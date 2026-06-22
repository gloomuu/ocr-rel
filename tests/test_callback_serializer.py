from ocr_rel.clients.platform_utils import is_platform_success_code
from ocr_rel.models.schemas import CallbackPayload, TypeResult
from ocr_rel.services.callback_serializer import serialize_callback_payload


def test_is_platform_success_code() -> None:
    assert is_platform_success_code(0)
    assert is_platform_success_code("0")
    assert not is_platform_success_code(1)
    assert not is_platform_success_code("1")


def test_serialize_callback_payload_total_assets_as_number() -> None:
    payload = CallbackPayload(
        registrationId="reg-001",
        results=[
            TypeResult(
                type=3,
                name="审计报告",
                detail=[
                    {
                        "companyName": "测试公司",
                        "totalAssets": "50000000",
                    }
                ],
            )
        ],
    )
    body = serialize_callback_payload(payload)
    assert body["results"][0]["name"] == "审计报告"
    assert body["results"][0]["detail"][0]["totalAssets"] == 50000000
    assert isinstance(body["results"][0]["detail"][0]["totalAssets"], int)


def test_serialize_callback_payload_keeps_credit_proof_fields() -> None:
    payload = CallbackPayload(
        registrationId="reg-002",
        results=[
            TypeResult(
                type=9,
                name="董监高信用证明",
                detail=[
                    {
                        "executedPersonName": "张三",
                        "queryResult": "暂无失信记录",
                        "personnel": "张三",
                    }
                ],
            )
        ],
    )
    body = serialize_callback_payload(payload)
    detail = body["results"][0]["detail"][0]
    assert detail["executedPersonName"] == "张三"
    assert detail["queryResult"] == "暂无失信记录"
    assert detail["personnel"] == "张三"
