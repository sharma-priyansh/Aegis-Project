"""Unit tests for approval signing + capability + param validation (ADR-014/015)."""
import time
import pytest
from aegis_common.security import (ActionValidationError, mint_credential, sign_approval,
                                   validate_action_params, verify_approval)


def test_sign_and_verify_roundtrip():
    rec = {"plan_id": "p", "incident_id": "i", "decision": "approved", "fencing_token": 5}
    sig = sign_approval(rec)
    assert verify_approval(rec, sig)


def test_tampered_record_fails_verification():
    rec = {"plan_id": "p", "fencing_token": 5}
    sig = sign_approval(rec)
    rec["fencing_token"] = 6
    assert not verify_approval(rec, sig)


def test_capability_valid_then_expires():
    cap = mint_credential(incident_id="i", plan_id="p", fencing_token=1,
                          namespace="default", ttl_seconds=1)
    assert cap.is_valid()
    assert not cap.is_valid(now=time.time() + 2)


def test_capability_signature_is_tamper_evident():
    cap = mint_credential(incident_id="i", plan_id="p", fencing_token=1, namespace="default")
    cap.namespace = "kube-system"   # attacker widens scope
    assert not cap.is_valid()


def test_param_validation_requires_keys():
    schema = {"required": ["namespace", "deployment"]}
    validate_action_params("restart_deployment", {"namespace": "d", "deployment": "api"}, schema)
    with pytest.raises(ActionValidationError):
        validate_action_params("restart_deployment", {"namespace": "d"}, schema)
