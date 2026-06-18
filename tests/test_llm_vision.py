from ocr_rel.llm.vision import model_supports_vision


def test_model_supports_vision_detects_multimodal_models() -> None:
    assert model_supports_vision("qwen-vl-plus") is True
    assert model_supports_vision("qwen2.5-vl-7b-instruct") is True
    assert model_supports_vision("gpt-4o") is True


def test_model_supports_vision_rejects_text_only_models() -> None:
    assert model_supports_vision("qwen-plus") is False
    assert model_supports_vision("qwen-turbo") is False
