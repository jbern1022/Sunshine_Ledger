import boto3
import pytest
from botocore.stub import Stubber

from app.cognito_provider import CognitoProvider
from app.identity import InvalidCredentials

POOL, CLIENT = "us-east-1_Test", "client-1"


@pytest.fixture
def setup():
    c = boto3.client("cognito-idp", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y")
    return c, Stubber(c), CognitoProvider(c, POOL, CLIENT)


def user_attrs(verified="true"):
    return {"Username": "u", "UserAttributes": [
        {"Name": "sub", "Value": "sub-9"}, {"Name": "email", "Value": "a@example.org"}, {"Name": "email_verified", "Value": verified},
    ]}


def test_password_sign_in_asks_cognito_to_vouch_and_keeps_no_token(setup):
    c, s, p = setup
    s.add_response("initiate_auth", {"AuthenticationResult": {"AccessToken": "AT", "IdToken": "IT", "RefreshToken": "RT"}},
                   {"ClientId": CLIENT, "AuthFlow": "USER_PASSWORD_AUTH", "AuthParameters": {"USERNAME": "a@example.org", "PASSWORD": "pw"}})
    s.add_response("get_user", user_attrs(), {"AccessToken": "AT"})
    with s:
        o = p.authenticate("a@example.org", "pw")
    assert (o.sub, o.email, o.email_verified, o.factors) == ("sub-9", "a@example.org", True, frozenset({"pwd"}))
    assert "AT" not in repr(o) and "RT" not in repr(o)


def test_unverified_email_is_reported_not_hidden(setup):
    c, s, p = setup
    s.add_response("initiate_auth", {"AuthenticationResult": {"AccessToken": "AT"}})
    s.add_response("get_user", user_attrs("false"))
    with s:
        assert p.authenticate("a@example.org", "pw").email_verified is False


@pytest.mark.parametrize("code", ["NotAuthorizedException", "UserNotFoundException", "UserNotConfirmedException", "PasswordResetRequiredException"])
def test_credential_failures_all_look_the_same(setup, code):
    c, s, p = setup
    s.add_client_error("initiate_auth", service_error_code=code)
    with s, pytest.raises(InvalidCredentials):
        p.authenticate("a@example.org", "pw")


def test_a_real_fault_is_not_turned_into_a_sign_in_answer(setup):
    from botocore.exceptions import ClientError
    c, s, p = setup
    s.add_client_error("initiate_auth", service_error_code="InternalErrorException")
    with s, pytest.raises(ClientError):
        p.authenticate("a@example.org", "pw")


def test_totp_challenge_then_code_reports_both_factors(setup):
    c, s, p = setup
    s.add_response("initiate_auth", {"ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": "SESSION-0123456789-ABCDEF", "ChallengeParameters": {}})
    s.add_response("respond_to_auth_challenge", {"AuthenticationResult": {"AccessToken": "AT"}}, {
        "ClientId": CLIENT, "ChallengeName": "SOFTWARE_TOKEN_MFA", "Session": "SESSION-0123456789-ABCDEF",
        "ChallengeResponses": {"USERNAME": "a@example.org", "SOFTWARE_TOKEN_MFA_CODE": "123456"}})
    s.add_response("get_user", user_attrs())
    with s:
        first = p.authenticate("a@example.org", "pw")
        assert first.challenge == "totp" and first.sub == ""
        done = p.verify_totp(first.challenge_token, "123456")
    assert done.factors == frozenset({"pwd", "totp"}) and done.sub == "sub-9"


def test_an_unsupported_challenge_fails_closed_and_a_bad_code_is_invalid(setup):
    c, s, p = setup
    s.add_response("initiate_auth", {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "SESSION-0123456789-ABCDEF", "ChallengeParameters": {}})
    s.add_client_error("respond_to_auth_challenge", service_error_code="CodeMismatchException")
    with s:
        with pytest.raises(InvalidCredentials):
            p.authenticate("a@example.org", "pw")
        with pytest.raises(InvalidCredentials):
            p.verify_totp("a@example.org\nSESSION-0123456789-ABCDEF", "000000")
    with pytest.raises(InvalidCredentials):
        p.verify_totp("malformed", "1")


def test_client_secret_adds_a_secret_hash(setup):
    c, s, _ = setup
    p = CognitoProvider(c, POOL, CLIENT, client_secret="shh")
    seen = {}
    c.meta.events.register("before-parameter-build.cognito-idp.InitiateAuth", lambda params, **kw: seen.update(params["AuthParameters"]))
    s.add_response("initiate_auth", {"AuthenticationResult": {"AccessToken": "AT"}})
    s.add_response("get_user", user_attrs())
    with s:
        p.authenticate("a@example.org", "pw")
    assert "SECRET_HASH" in seen and len(seen["SECRET_HASH"]) > 20


def test_reset_confirms_then_reads_the_sub_and_delete_is_idempotent(setup):
    c, s, p = setup
    s.add_response("confirm_forgot_password", {}, {"ClientId": CLIENT, "Username": "a@example.org", "ConfirmationCode": "999", "Password": "new"})
    s.add_response("admin_get_user", user_attrs(), {"UserPoolId": POOL, "Username": "a@example.org"})
    s.add_client_error("admin_delete_user", service_error_code="UserNotFoundException")
    s.add_response("admin_delete_user", {}, {"UserPoolId": POOL, "Username": "sub-9"})
    with s:
        assert p.confirm_password_reset("a@example.org", "999", "new") == "sub-9"
        p.delete_user("sub-9")  # already gone: fine
        p.delete_user("sub-9")
    s.add_client_error("confirm_forgot_password", service_error_code="ExpiredCodeException")
    with s, pytest.raises(InvalidCredentials):
        p.confirm_password_reset("a@example.org", "old", "new")
