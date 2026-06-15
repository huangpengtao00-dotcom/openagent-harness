from error_response import AppError, to_error_response


def test_app_error_message_is_visible_to_client():
    response = to_error_response(AppError("invalid token", status_code=401))
    assert response == {"status_code": 401, "body": {"error": "invalid token"}}


def test_internal_error_hides_implementation_details_by_default():
    response = to_error_response(RuntimeError("database password leaked in stack"))
    assert response["status_code"] == 500
    assert response["body"]["error"] == "internal server error"
    assert "password" not in response["body"]["error"]


def test_debug_mode_can_return_details_for_local_diagnosis():
    response = to_error_response(RuntimeError("database unavailable"), debug=True)
    assert response == {"status_code": 500, "body": {"error": "database unavailable"}}
