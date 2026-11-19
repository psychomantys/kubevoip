from kubevoip.models import AsteriskPoolSpec, SIPGatewaySpec
from kubevoip.platform_render import render_kamailio_config, render_worker_configs


def gateway_spec() -> SIPGatewaySpec:
    return SIPGatewaySpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "networkProfileRef": {"name": "public"},
            "mediaRelayRef": {"name": "home"},
        }
    )


def homer_gateway_spec(capture_mode: str = "transaction") -> SIPGatewaySpec:
    return SIPGatewaySpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "networkProfileRef": {"name": "public"},
            "mediaRelayRef": {"name": "home"},
            "observability": {
                "capture": {
                    "enabled": True,
                    "type": "Homer",
                    "hepAddress": "homer-heplify.telemetry.svc.cluster.local",
                    "hepPort": 9060,
                    "hepTransport": "udp",
                    "captureMode": capture_mode,
                    "includePayload": True,
                }
            },
        }
    )


def sip_headers_gateway_spec() -> SIPGatewaySpec:
    return SIPGatewaySpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "networkProfileRef": {"name": "public"},
            "mediaRelayRef": {"name": "home"},
            "observability": {"sipHeaders": {"enabled": True}},
        }
    )


def sdp_gateway_spec() -> SIPGatewaySpec:
    return SIPGatewaySpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "networkProfileRef": {"name": "public"},
            "mediaRelayRef": {"name": "home"},
            "observability": {"sdp": {"enabled": True}},
        }
    )


def test_kamailio_renders_resolved_ipv4_aliases_while_keeping_hostname_advertise():
    rendered = render_kamailio_config(
        gateway_spec(),
        "home",
        "test",
        "sip.example.com",
        "sip-internal.example.com",
        ["udp:rtpengine:2223"],
        external_address_aliases=["198.51.100.10", "203.0.113.20"],
        internal_address_aliases=["10.0.0.10"],
    )

    assert '#!define ADVERTISED_ADDR "sip.example.com"' in rendered
    assert '#!define INTERNAL_ADDR "sip-internal.example.com"' in rendered
    assert "alias=ADVERTISED_ADDR:5060" in rendered
    assert "alias=INTERNAL_ADDR:5060" in rendered
    assert "alias=198.51.100.10:5060" in rendered
    assert "alias=203.0.113.20:5060" in rendered
    assert "alias=10.0.0.10:5060" in rendered
    assert "listen=udp:0.0.0.0:5060 advertise ADVERTISED_ADDR:5060" in rendered


def test_kamailio_uses_database_backed_runtime_routing():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert 'loadmodule "sqlops.so"' in rendered
    assert 'modparam("sqlops", "sqlcon", "kubevoip=>__DBURL__")' in rendered
    assert "kubevoip_sip_trunk_cidr" in rendered
    assert "kubevoip_dial_policy_scope" in rendered
    assert "kubevoip_call_route" in rendered
    assert "kubevoip_sip_user" in rendered
    assert "kubevoip_sip_trunk" in rendered
    assert "kubevoip_voicemail_mailbox" in rendered
    assert "proxy_authorize" in rendered
    assert 'lookup("location")' in rendered
    assert 'uac_auth_mode("1")' in rendered
    assert "rtpengine_offer" in rendered
    assert "provider.example.net" not in rendered
    assert "provider-password" not in rendered
    assert "provider-user" not in rendered
    assert "KUBEVOIP_TRUNK_" not in rendered
    assert '" + $aU + "' in rendered
    assert '" + $avp(caller_policy) + "' in rendered
    assert '" + $rU + "' in rendered
    assert 'sql_query("kubevoip", "$var(caller_query)", "caller")' in rendered
    assert "namespace='test'" in rendered
    assert "gateway_name='home'" in rendered
    assert "namespace='KUBEVOIP_NAMESPACE'" not in rendered
    assert "log_stderror=yes" in rendered
    assert 'loadmodule "xlog.so"' in rendered
    assert "kubevoip_sip_event" in rendered
    assert 'loadmodule "siptrace.so"' not in rendered
    assert "duplicate_uri" not in rendered
    assert "kubevoip_sip_headers" not in rendered
    assert "kubevoip_sdp_body" not in rendered
    assert "kubevoip_sip_message" not in rendered


def test_kamailio_renders_voicemail_fallback_routes():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert "route[RELAY_USER]" in rendered
    assert "failure_route[VOICEMAIL_FALLBACK]" in rendered
    assert "route[SEND_TO_VOICEMAIL]" in rendered
    assert "X-KubeVoIP-Mailbox" in rendered
    assert "$avp(vm_mailbox) = $dbr(route=>[0,10]);" in rendered
    assert "$var(vm_fr) = $avp(vm_timeout) * 1000;" in rendered
    assert "t_set_fr($var(vm_fr), $var(vm_fr));" in rendered
    assert 'rtpengine_offer("replace-origin replace-session-connection direction=external direction=external");' in rendered
    assert 'rtpengine_offer("replace-origin replace-session-connection direction=external direction=internal");' in rendered
    assert 'rtpengine_answer("replace-origin replace-session-connection direction=internal direction=external");' in rendered
    assert 'rtpengine_answer("replace-origin replace-session-connection direction=external direction=external");' in rendered
    assert "media_target=asterisk" in rendered


def test_kamailio_renders_mwi_routes():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert 'loadmodule "presence.so"' in rendered
    assert 'loadmodule "presence_mwi.so"' in rendered
    assert 'modparam("presence", "db_url", "__DBURL__")' in rendered
    assert 'modparam("presence_mwi", "default_expires", 3600)' in rendered
    assert 'is_method("SUBSCRIBE") && $hdr(Event) =~ "message-summary"' in rendered
    assert 'is_method("PUBLISH") && $hdr(Event) =~ "message-summary"' in rendered
    assert "route[HANDLE_MWI_SUBSCRIBE]" in rendered
    assert "route[HANDLE_MWI_PUBLISH]" in rendered
    assert "handle_subscribe();" in rendered
    assert "handle_publish();" in rendered
    assert "route(SEND_MWI_NOTIFY_TO_CONTACTS);" in rendered
    assert "uac_req_send()" in rendered
    assert "Messages-Waiting" in rendered
    assert "Voice-Message" in rendered


def test_worker_configs_include_odbc_voicemail_when_enabled():
    spec = AsteriskPoolSpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "applications": {"voicemail": {"enabled": True}},
        }
    )
    configs = render_worker_configs(
        spec,
        {"host": "postgres.test.svc", "port": "5432", "dbname": "kubevoip", "user": "app", "password": "secret"},
    )

    assert "VoiceMailMain()" in configs["extensions.conf"]
    assert "VoiceMail(${KUBEVOIP_MAILBOX}@default,u)" in configs["extensions.conf"]
    assert "allow=ulaw" in configs["pjsip.conf"]
    assert "allow=alaw" in configs["pjsip.conf"]
    assert "voicemail => odbc,kubevoip,voicemail" in configs["extconfig.conf"]
    assert "odbcstorage=kubevoip" in configs["voicemail.conf"]
    assert "forcename=yes" in configs["voicemail.conf"]
    assert "forcegreetings=yes" in configs["voicemail.conf"]
    assert "externnotify=/usr/local/bin/kubevoip-mwi-publish" in configs["voicemail.conf"]
    assert "Driver=PostgreSQL Unicode" in configs["odbc.ini"]
    assert "password => secret" in configs["res_odbc.conf"]


def test_worker_configs_can_preselect_voicemail_main_mailbox():
    spec = AsteriskPoolSpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "applications": {"voicemail": {"enabled": True, "mainMailbox": "100"}},
        }
    )
    configs = render_worker_configs(
        spec,
        {"host": "postgres.test.svc", "port": "5432", "dbname": "kubevoip", "user": "app", "password": "secret"},
    )

    assert "VoiceMailMain(100@default)" in configs["extensions.conf"]
    assert "VoiceMailMain()" not in configs["extensions.conf"]


def test_worker_configs_append_extra_fragments():
    spec = AsteriskPoolSpec.model_validate(
        {
            "extensions": {"extra": "exten => 601,1,Hangup()"},
            "pjsip": {"extra": "[custom]\ntype=endpoint\ncontext=applications"},
            "rtp": {"extra": "icesupport=yes"},
        }
    )
    configs = render_worker_configs(spec)

    assert "exten => 600,1,Answer()" in configs["extensions.conf"]
    assert "exten => 601,1,Hangup()" in configs["extensions.conf"]
    assert configs["extensions.conf"].index("exten => 600,1,Answer()") < configs["extensions.conf"].index(
        "exten => 601,1,Hangup()"
    )
    assert "allow=ulaw" in configs["pjsip.conf"]
    assert "[custom]" in configs["pjsip.conf"]
    assert "rtpstart=10000" in configs["rtp.conf"]
    assert "icesupport=yes" in configs["rtp.conf"]
    assert configs["extensions.conf"].endswith("\n")
    assert configs["pjsip.conf"].endswith("\n")
    assert configs["rtp.conf"].endswith("\n")


def test_worker_configs_override_replaces_template():
    spec = AsteriskPoolSpec.model_validate(
        {
            "extensions": {"override": "[custom]\nexten => 900,1,Hangup()\n"},
            "pjsip": {"override": "[custom]\ntype=endpoint\n"},
            "rtp": {"override": "[general]\nrtpstart=12000\nrtpend=12999\n"},
        }
    )
    configs = render_worker_configs(spec)

    assert configs["extensions.conf"] == "[custom]\nexten => 900,1,Hangup()\n"
    assert "exten => 600,1,Answer()" not in configs["extensions.conf"]
    assert configs["pjsip.conf"] == "[custom]\ntype=endpoint\n"
    assert "allow=ulaw" not in configs["pjsip.conf"]
    assert configs["rtp.conf"] == "[general]\nrtpstart=12000\nrtpend=12999\n"
    assert "rtpstart=10000" not in configs["rtp.conf"]


def test_worker_configs_override_takes_precedence_over_extra():
    spec = AsteriskPoolSpec.model_validate(
        {
            "extensions": {"extra": "exten => 601,1,Hangup()", "override": "[only]\nexten => 900,1,Hangup()"},
            "pjsip": {"extra": "[ignored]\ntype=aor", "override": "[only]\ntype=endpoint"},
            "rtp": {"extra": "icesupport=yes", "override": "[general]\nrtpstart=12000"},
        }
    )
    configs = render_worker_configs(spec)

    assert configs["extensions.conf"] == "[only]\nexten => 900,1,Hangup()\n"
    assert "exten => 600" not in configs["extensions.conf"]
    assert "exten => 601" not in configs["extensions.conf"]
    assert configs["pjsip.conf"] == "[only]\ntype=endpoint\n"
    assert "[ignored]" not in configs["pjsip.conf"]
    assert configs["rtp.conf"] == "[general]\nrtpstart=12000\n"
    assert "icesupport=yes" not in configs["rtp.conf"]
    assert "rtpstart=10000" not in configs["rtp.conf"]


def test_kamailio_loads_policy_before_consuming_credentials():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert rendered.index("route(LOAD_AUTHENTICATED_POLICY);") < rendered.index("consume_credentials();")


def test_kamailio_record_route_uses_internal_and_external_addresses():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert 'record_route_preset("10.0.0.10:$Rp;r2=on", "198.51.100.10:$Rp;r2=on")' in rendered
    assert 'record_route_preset("198.51.100.10:$Rp;r2=on", "10.0.0.10:$Rp;r2=on")' in rendered


def test_kamailio_listens_on_configured_transports_and_ports():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])
    assert "listen=udp:0.0.0.0:5060 advertise ADVERTISED_ADDR:5060" in rendered
    assert "listen=tcp:0.0.0.0:5060 advertise ADVERTISED_ADDR:5060" in rendered
    assert "if (proto == TCP)" in rendered
    assert 'record_route_preset("10.0.0.10:$Rp;r2=on", "198.51.100.10:$Rp;transport=tcp;r2=on")' in rendered
    assert 'record_route_preset("198.51.100.10:$Rp;r2=on", "10.0.0.10:$Rp;transport=tcp;r2=on")' in rendered

    multi = SIPGatewaySpec.model_validate(
        {**gateway_spec().model_dump(by_alias=True), "transports": ["udp"], "ports": [5060, 5080]}
    )
    rendered = render_kamailio_config(
        multi,
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
        external_address_aliases=["198.51.100.10"],
        internal_address_aliases=["10.0.0.10"],
    )
    assert "alias=ADVERTISED_ADDR:5060" in rendered
    assert "alias=ADVERTISED_ADDR:5080" in rendered
    assert "alias=198.51.100.10:5060" in rendered
    assert "alias=198.51.100.10:5080" in rendered
    assert "alias=10.0.0.10:5060" in rendered
    assert "alias=10.0.0.10:5080" in rendered
    assert "listen=udp:0.0.0.0:5060 advertise ADVERTISED_ADDR:5060" in rendered
    assert "listen=udp:0.0.0.0:5080 advertise ADVERTISED_ADDR:5080" in rendered
    assert "listen=tcp:" not in rendered
    assert "transport=tcp" not in rendered
    assert 'append_hf("Contact: <sip:asterisk@" + ADVERTISED_ADDR + ":5060>\\r\\n");' in rendered
    assert 'modparam("presence", "server_address", "sip:ADVERTISED_ADDR:5060")' in rendered

    custom_primary = SIPGatewaySpec.model_validate(
        {**gateway_spec().model_dump(by_alias=True), "transports": ["udp"], "ports": [5080, 5060]}
    )
    rendered = render_kamailio_config(
        custom_primary, "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"]
    )
    assert 'append_hf("Contact: <sip:asterisk@" + ADVERTISED_ADDR + ":5080>\\r\\n");' in rendered
    assert 'modparam("presence", "server_address", "sip:ADVERTISED_ADDR:5080")' in rendered


def test_kamailio_uses_single_record_route_when_addresses_match():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "198.51.100.10", ["udp:rtpengine:2223"])
    assert "record_route();" in rendered
    assert "record_route_preset" not in rendered


def test_kamailio_homer_capture_is_opt_in():
    rendered = render_kamailio_config(homer_gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert 'loadmodule "siptrace.so"' in rendered
    assert 'modparam("siptrace", "trace_to_database", 0)' in rendered
    assert 'modparam("siptrace", "trace_flag"' not in rendered
    assert 'modparam("siptrace", "hep_mode_on", 1)' in rendered
    assert 'modparam("siptrace", "hep_version", 3)' in rendered
    assert 'modparam("siptrace", "duplicate_uri", "sip:homer-heplify.telemetry.svc.cluster.local:9060")' in rendered
    assert "setflag(22);" not in rendered
    assert 'sip_trace_mode("t");' in rendered
    assert "sip_trace();" not in rendered


def test_kamailio_homer_capture_supports_dialog_mode():
    rendered = render_kamailio_config(homer_gateway_spec("dialog"), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert 'sip_trace_mode("d");' in rendered


def test_kamailio_can_log_sip_headers_to_stdout():
    rendered = render_kamailio_config(sip_headers_gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert "kubevoip_sip_message" in rendered
    assert "route(LOG_SIP_MESSAGE);" in rendered
    assert "$msg(fline)" in rendered
    assert '$var(cr) = "0d";' in rendered
    assert "$var(cr) = $(var(cr){s.decode.hexa});" in rendered
    assert '$var(lf) = "0a";' in rendered
    assert "$var(lf) = $(var(lf){s.decode.hexa});" in rendered
    assert "$(msg(hdrs){s.replace,$var(cr),\\\\r}{s.replace,$var(lf),\\\\n})" in rendered


def _gateway_with_fixes(
    *,
    aggressive_sbc: bool = True,
    in_dialog_validation: bool = True,
) -> SIPGatewaySpec:
    return SIPGatewaySpec.model_validate(
        {
            "databaseSecretRef": {"name": "db"},
            "networkProfileRef": {"name": "public"},
            "mediaRelayRef": {"name": "home"},
            "fix": {
                "aggressiveSbcPrivateContact": {"enabled": aggressive_sbc},
                "inDialogValidation": {"enabled": in_dialog_validation},
            },
        }
    )


def _gateway_with_aggressive_sbc(*, enabled: bool) -> SIPGatewaySpec:
    return _gateway_with_fixes(aggressive_sbc=enabled, in_dialog_validation=True)


def test_kamailio_aggressive_sbc_private_contact_fix_enabled_by_default():
    rendered = render_kamailio_config(gateway_spec(), "home", "test", "198.51.100.10", "10.0.0.10", ["udp:rtpengine:2223"])

    assert 'loadmodule "htable.so"' in rendered
    assert 'modparam("htable", "htable", "calleedu=>size=16;autoexpire=7200;")' in rendered
    assert "route[FIX_CALLEE_DEST]" in rendered
    assert "route[LOAD_CALLEE_DEST]" in rendered
    assert "route[STORE_CALLEE_DEST]" in rendered
    assert "route[CLEAR_CALLEE_DEST]" in rendered
    assert "stage=ack_force_callee" in rendered
    assert "stage=indialog_force_callee" in rendered
    assert "stage=asterisk_callee_stored" in rendered
    assert "stage=contact_rewritten" in rendered
    assert 'append_hf("Contact: <sip:asterisk@" + ADVERTISED_ADDR + ":5060>\\r\\n");' in rendered
    assert '$dlg_var(sbc_trunk) = "1";' in rendered
    assert '$dlg_var(sbc_trunk) == "1"' in rendered
    assert "stage=indialog_self_ruri_fixed" in rendered
    assert "uri == myself" in rendered
    assert "$sht(calleedu=>$ci) = $du;" in rendered
    assert "kubevoip_asterisk_callee" in rendered
    assert "route(LOAD_CALLEE_DEST);" in rendered
    assert "route(STORE_CALLEE_DEST);" in rendered
    assert "route[BIND_ASTERISK_REPLY_DEST]" in rendered
    assert "stage=asterisk_dest_bound" in rendered
    assert "update kubevoip_asterisk_callee set destination=" in rendered
    assert "$(ci{s.replace,',''})" in rendered
    assert "$(du{s.replace,',''})" in rendered
    assert "+ $var(du_esc) +" in rendered
    assert "if (isflagset(1))" in rendered
    assert "if (!isflagset(1))" in rendered
    assert "$dlg_var(callee_du)" not in rendered
    store_idx = rendered.index("route(STORE_CALLEE_DEST);")
    trunk_flag_idx = rendered.index('$dlg_var(sbc_trunk) = "1";', store_idx)
    assert trunk_flag_idx > store_idx
    loose_idx = rendered.index("if (loose_route())")
    self_ruri_idx = rendered.index("stage=indialog_self_ruri_fixed")
    relay_idx = rendered.index("route(RELAY);", self_ruri_idx)
    assert loose_idx < self_ruri_idx < relay_idx
    load_idx = rendered.index("route[LOAD_CALLEE_DEST]")
    sht_idx = rendered.index("$sht(calleedu=>$ci) != $null", load_idx)
    sql_idx = rendered.index("kubevoip_asterisk_callee", load_idx)
    assert sht_idx < sql_idx
    manage_reply = rendered[rendered.index("onreply_route[MANAGE_REPLY]") :]
    bind_call_idx = manage_reply.index("route(BIND_ASTERISK_REPLY_DEST);")
    rewrite_idx = manage_reply.index("stage=contact_rewritten")
    assert bind_call_idx < rewrite_idx
    # No hardcoded LB / public hostname IP aliases in the rendered script.
    assert "alias=18." not in rendered
    assert "voip.weni.ai" not in rendered
    assert 'modparam("dialog", "default_timeout"' not in rendered
    assert "is_myself" not in rendered


def test_kamailio_aggressive_sbc_private_contact_fix_can_be_disabled():
    rendered = render_kamailio_config(
        _gateway_with_fixes(aggressive_sbc=False, in_dialog_validation=False),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
    )

    assert 'loadmodule "htable.so"' not in rendered
    assert "route[FIX_CALLEE_DEST]" not in rendered
    assert "route[LOAD_CALLEE_DEST]" not in rendered
    assert "route[BIND_ASTERISK_REPLY_DEST]" not in rendered
    assert "stage=ack_force_callee" not in rendered
    assert "stage=contact_rewritten" not in rendered
    assert "stage=asterisk_dest_bound" not in rendered
    assert "stage=indialog_self_ruri_fixed" not in rendered
    assert "sbc_trunk" not in rendered
    assert "kubevoip_asterisk_callee" not in rendered
    assert "calleedu" not in rendered
    assert 'if (is_method("BYE|CANCEL"))' in rendered
    assert "if (loose_route())" in rendered
    assert "route(RELAY);" in rendered


def test_kamailio_aggressive_sbc_private_contact_keeps_private_ruri():
    rendered = render_kamailio_config(
        _gateway_with_aggressive_sbc(enabled=True),
        "home",
        "test",
        "sip.example.com",
        "sip.example.com",
        ["udp:rtpengine:2223"],
    )

    assert 'if ($rd =~ "^(10\\\\.|192\\\\.168\\\\.|172\\\\.(1[6-9]|2[0-9]|3[0-1])\\\\.)")' in rendered
    assert "stage=contact_rewritten" in rendered
    assert "insert into kubevoip_asterisk_callee" in rendered
    assert "select destination from kubevoip_asterisk_callee" in rendered
    assert "delete from kubevoip_asterisk_callee" in rendered
    assert "update kubevoip_asterisk_callee set destination=" in rendered


def test_kamailio_bind_asterisk_reply_dest_updates_stores_before_contact_rewrite():
    rendered = render_kamailio_config(
        gateway_spec(),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
    )

    assert "route[BIND_ASTERISK_REPLY_DEST]" in rendered
    assert '$dlg_var(media_target) != "asterisk"' in rendered
    assert "$(ct{nameaddr.uri}{uri.host})" in rendered
    assert "$(ct{nameaddr.uri}{uri.port})" in rendered
    assert "ct.fields.uri" not in rendered
    assert "stage=asterisk_dest_bound" in rendered
    assert "update kubevoip_asterisk_callee set destination=" in rendered
    assert "update kubevoip_dialog set downstream_uri=" in rendered
    manage_reply = rendered[rendered.index("onreply_route[MANAGE_REPLY]") :]
    assert manage_reply.index("route(BIND_ASTERISK_REPLY_DEST);") < manage_reply.index("stage=contact_rewritten")


def test_kamailio_bind_asterisk_reply_dest_with_only_aggressive_sbc():
    rendered = render_kamailio_config(
        _gateway_with_fixes(aggressive_sbc=True, in_dialog_validation=False),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
    )

    assert "route[BIND_ASTERISK_REPLY_DEST]" in rendered
    assert "update kubevoip_asterisk_callee set destination=" in rendered
    assert "update kubevoip_dialog set downstream_uri=" not in rendered


def test_kamailio_bind_asterisk_reply_dest_with_only_in_dialog_validation():
    rendered = render_kamailio_config(
        _gateway_with_fixes(aggressive_sbc=False, in_dialog_validation=True),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
    )

    assert "route[BIND_ASTERISK_REPLY_DEST]" in rendered
    assert "update kubevoip_dialog set downstream_uri=" in rendered
    assert "update kubevoip_asterisk_callee set destination=" not in rendered
    assert "calleedu" not in rendered


def test_kamailio_in_dialog_validation_enabled_by_default():
    rendered = render_kamailio_config(
        gateway_spec(),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
        local_networks=["10.0.0.0/8"],
    )

    assert 'loadmodule "ipops.so"' in rendered
    assert 'loadmodule "rtimer.so"' in rendered
    assert "route[GUARD_INDIALOG_DEST]" in rendered
    assert "route[LOAD_DIALOG]" in rendered
    assert "route[STORE_DIALOG]" in rendered
    assert "route[CLEAR_DIALOG]" in rendered
    assert "route[PURGE_EXPIRED_ROWS]" in rendered
    assert "is_known_dlg()" in rendered
    assert 'if (is_method("CANCEL"))' in rendered
    assert "t_check_trans()" in rendered
    cancel_idx = rendered.index('if (is_method("CANCEL"))')
    known_idx = rendered.index("is_known_dlg()")
    delete_idx = rendered.index("stage=rtpengine_delete", known_idx)
    guard_idx = rendered.index("route(GUARD_INDIALOG_DEST);")
    relay_idx = rendered.index("route(RELAY);", guard_idx)
    assert cancel_idx < known_idx < delete_idx
    assert guard_idx < relay_idx
    assert "stage=indialog_rejected" in rendered
    assert "stage=cancel_rejected" in rendered
    assert "stage=indialog_dest_forbidden" in rendered
    assert "stage=dialog_stored" in rendered
    assert "stage=asterisk_dest_bound" in rendered
    assert "kubevoip_dialog" in rendered
    assert "update kubevoip_dialog set downstream_uri=" in rendered
    assert 'ip_is_in_subnet("$si", "10.0.0.0/8")' in rendered
    assert "delete from kubevoip_dialog where expires_at < now()" in rendered
    assert "delete from kubevoip_asterisk_callee where expires_at < now()" in rendered
    assert 'send_reply("481", "Call/Transaction Does Not Exist");' in rendered
    guard = rendered[rendered.index("route[GUARD_INDIALOG_DEST]") : rendered.index("route[PURGE_EXPIRED_ROWS]")]
    assert "$du = $avp(callee_du);" in guard
    assert "$du = $avp(dlg_downstream);" in guard
    assert "$du == $avp(callee_du)" not in guard


def test_kamailio_in_dialog_validation_can_be_disabled():
    rendered = render_kamailio_config(
        _gateway_with_fixes(aggressive_sbc=True, in_dialog_validation=False),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
    )

    assert 'loadmodule "ipops.so"' not in rendered
    assert 'loadmodule "rtimer.so"' not in rendered
    assert "route[GUARD_INDIALOG_DEST]" not in rendered
    assert "route[LOAD_DIALOG]" not in rendered
    assert "is_known_dlg()" not in rendered
    assert 'if (is_method("BYE|CANCEL"))' in rendered
    assert "stage=dialog_not_found" in rendered
    assert 'send_reply("404", "Dialog not found");' in rendered
    assert "kubevoip_dialog" not in rendered
    assert "sbc_trunk" in rendered
    assert "stage=indialog_self_ruri_fixed" in rendered


def test_kamailio_can_include_sdp_body_in_sip_message_log():
    rendered = render_kamailio_config(
        SIPGatewaySpec.model_validate(
            {
                "databaseSecretRef": {"name": "db"},
                "networkProfileRef": {"name": "public"},
                "mediaRelayRef": {"name": "home"},
                "observability": {"sipHeaders": {"enabled": True}, "sdp": {"enabled": True}},
            }
        ),
        "home",
        "test",
        "198.51.100.10",
        "10.0.0.10",
        ["udp:rtpengine:2223"],
    )

    assert "kubevoip_sip_message" in rendered
    assert "route(LOG_SIP_MESSAGE);" in rendered
    assert 'has_body("application/sdp")' in rendered
    assert "$(rb{s.replace,$var(cr),\\\\r}{s.replace,$var(lf),\\\\n})" in rendered
