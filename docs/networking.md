# Networking

KubeVoIP chooses external addresses in this order:

1. RTPengine replica override.
2. Component-level override.
3. Explicit value from the referenced `NetworkProfile`.
4. The component LoadBalancer Service ingress.
5. An unresolved-address condition for externally exposed components.

For cluster-local `ClusterIP` components, KubeVoIP uses the managed Service DNS
name.

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

### Multi-A LoadBalancer hostnames

When the resolved external (or internal) address is a hostname, the operator
resolves its IPv4 `A` records during reconcile (IPv6/`AAAA` is not used yet):

- Sorted unique IPs are stored on status as `advertisedIps` (and
  `internalAdvertisedIps` on `SIPGateway`, or per-replica `advertisedIps` on
  `MediaRelay` status relays).
- Kamailio keeps the hostname in `advertise`, Record-Route, and Contact rewrite
  targets, and adds `alias=<ip>:5060` for each resolved IPv4 so in-dialog
  requests that use an NLB A-record IP still match `myself`.
- RTPengine no longer runs `getent` at startup. The operator passes explicit
  advertise IPs into `--interface`. One IP uses `external/$POD_IP!<ip>`; two or
  more use equal round-robin names `external:0`, `external:1`, … so SDP `c=`
  rotates across the current NLB front-door IPs.
- Pod template annotations (`kubevoip.com/advertised-ips`) and the Kamailio
  ConfigMap hash change when the IP set changes, which rolls the workloads.
- If DNS fails after a successful resolve, reconciliation keeps the last-known
  IP set from status (`UsingCachedAdvertisedIps`) and does not roll. A hostname
  that has never resolved remains a dependency error.

Prefer a single stable IP in `NetworkProfile` when the provider can allocate
one. Multi-A resolution is for cloud NLB DNS names that publish several IPv4
addresses.

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
testing. Destination recovery uses the stored Asterisk URI only (not hardcoded
LB IP aliases in that fix path). Separately, DNS-resolved NLB IPv4 aliases are
still rendered for `myself` matching as described above.

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

Forwarding needs the same public and private port numbers. Send UDP `5060` to
the Kamailio address. Send each RTPengine replica's assigned range to that
replica's address. Do not translate those ports.

`HostNetwork` avoids Kubernetes Service NAT for media but binds ports directly on
selected nodes. The cluster operator must handle scheduling, node public
addresses, firewall rules, and port conflicts.
