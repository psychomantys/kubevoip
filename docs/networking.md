# Networking

KubeVoIP chooses external addresses in this order:

1. RTPengine replica override.
2. Component-level override.
3. Explicit value from the referenced `NetworkProfile`.
4. The component LoadBalancer Service ingress.
5. An unresolved-address condition for externally exposed components.

For cluster-local `ClusterIP` components, KubeVoIP uses the managed Service DNS
name. If RTPengine receives a hostname, it resolves the hostname inside the Pod
before startup because SDP needs an IP address.

For LoadBalancer components without an explicit address, KubeVoIP creates the
managed Service and reports `WaitingForLoadBalancer` while its ingress is
pending. After MetalLB or the cloud provider assigns an address, reconciliation
starts or rolls the component with that advertised address.

`SIPGateway.spec.internalAddress` controls the SIP route advertised to internal
registered endpoints. If omitted, KubeVoIP uses the SIP gateway Service ingress
when available. Otherwise it uses the managed Service DNS name. This lets
trunk-facing dialogs advertise a public address while LAN phones receive an
internal Record-Route target for in-dialog requests such as `ACK`, `BYE`, and
re-INVITE.

Kamailio receives SIP, writes registrations to PostgreSQL, selects a route from
PostgreSQL runtime data, and asks an RTPengine replica to rewrite SDP. Direct
trunk-to-phone media flows through RTPengine without Asterisk. Calls to an
`AsteriskPool` application flow through RTPengine and one selected Asterisk pod.

IP-authenticated trunks trust only `SIPTrunk.spec.inbound.allowedSourceCidrs`.
Untrusted INVITEs receive a proxy-authentication challenge and must authenticate
as a `SIPUser`.

### Aggressive SBC + private Asterisk Contact

Some external SBCs (for example passwordless SIP trunks) rewrite the ACK
Request-URI to the public edge address when Asterisk advertises a private
`Contact`. After Kamailio consumes Record-Route, that hairpins the ACK and
Asterisk never completes the dialog (~32s SIP 408 / hangupcause 18).

By default, `SIPGateway.spec.fix.aggressiveSbcPrivateContact.enabled` is
`true`. Kamailio then:

- stores the Asterisk destination URI per Call-ID when routing to an
  `AsteriskPool` (or voicemail fallback) in PostgreSQL
  (`kubevoip_asterisk_callee`) as the shared source of truth, with a per-pod
  `htable` (`calleedu`) as an L1 cache for the common same-pod ACK path
- forces in-dialog `ACK` / `BYE` to that stored destination only for trusted
  trunks (`isflagset(1)`), and only when the Request-URI is not already a
  private cluster address — so Asterisk→SBC return-path traffic is not
  hairpinned back to Asterisk
- rewrites AsteriskPool `2xx` `Contact` to the gateway advertised address

Multi-replica SIPGateway deployments are safe: an ACK that lands on a different
Kamailio pod than the INVITE loads the destination from PostgreSQL, fills the
local L1 cache, then forces `$du`. Pod restart mid-call also recovers from
Postgres. Sticky NLB affinity is not required.

Set `enabled: false` to restore the previous Kamailio script for compatibility
testing. No load-balancer IP aliases are rendered; destination recovery uses the
stored Asterisk URI only.

`CallRoute` resources belong to a `CallScope`. `DialPolicy` resources define the
ordered scopes a caller can search. Authenticated SIP users use
`SIPUser.spec.dialPolicyRef`. Trusted inbound trunk calls use
`SIPTrunk.spec.inbound.dialPolicyRef`. Route selection sorts by policy scope
order, then route priority, then route resource name.

Outbound trunks can use Secret-backed caller ID and SIP digest credentials.
KubeVoIP stores caller ID and realm-bound HA1 runtime values in PostgreSQL. Raw
digest passwords are not stored, but HA1 is credential-equivalent for that SIP
realm. Protect PostgreSQL accordingly. Rendered ConfigMaps, statuses, Events,
and logs must not expose raw passwords or HA1.

Normal changes to SIP users, trunks, routes, scopes, policies, caller ID, and
digest credentials update PostgreSQL and do not roll Kamailio pods. Static
gateway/network changes can still roll pods.

`SIPGateway.spec.transports` selects the SIP transports Kamailio accepts. It
defaults to `["udp", "tcp"]`. `SIPGateway.spec.ports` selects the SIP listen
ports and defaults to `[5060]`. The gateway Service exposes one Service port for
each transport and port combination. A LoadBalancer Service that carries both
UDP and TCP needs a Kubernetes version and load balancer implementation with
mixed-protocol support (Kubernetes 1.26 or newer); set `transports: ["udp"]` if
yours does not.

Forwarding needs the same public and private port numbers. Send each enabled
transport and port to the Kamailio address. Send each RTPengine replica's assigned range to that
replica's address. Do not translate those ports.

`HostNetwork` avoids Kubernetes Service NAT for media but binds ports directly on
selected nodes. The cluster operator must handle scheduling, node public
addresses, firewall rules, and port conflicts.
