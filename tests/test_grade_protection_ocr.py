import pytest

from ocr_rel.services.grade_protection_ocr import merge_page_texts


def test_merge_page_texts_skips_empty_pages() -> None:
    merged = merge_page_texts(["首页内容", "", "  ", "第三页内容"])
    assert "--- 第 1 页 ---" in merged
    assert "首页内容" in merged
    assert "--- 第 4 页 ---" in merged
    assert "第三页内容" in merged
    assert "--- 第 2 页 ---" not in merged


@pytest.mark.asyncio
async def test_recognize_grade_protection_detail_merges_all_pages() -> None:
    from ocr_rel.services.grade_protection_ocr import recognize_grade_protection_detail

    class FakeEngine:
        async def recognize_image(self, image):  # noqa: ANN001
            del image
            if not hasattr(self, "count"):
                self.count = 0
            self.count += 1
            if self.count == 1:
                return "信息系统安全等级保护备案证明"
            return "单位名称：河南测试售电有限公司\n安全保护等级：第三级"

    detail, text = await recognize_grade_protection_detail(FakeEngine(), [object(), object()])
    assert "信息系统安全等级保护备案证明" in text
    assert "单位名称：河南测试售电有限公司" in text
    assert detail["companyName"] == "河南测试售电有限公司"
    assert detail["systemLevel"] == "三级"
    assert detail["copyrightOwner"] == ""
