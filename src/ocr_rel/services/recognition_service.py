from __future__ import annotations

from typing import Any, Awaitable, Callable

from ocr_rel.clients.platform_callback import PlatformCallbackClient
from ocr_rel.clients.platform_file import PlatformFileClient
from ocr_rel.logging_config import get_logger, log_ocr_text, log_result, log_step
from ocr_rel.models.schemas import (
    ATTACHMENT_TYPE_NAMES,
    CallbackPayload,
    FileRef,
    FileTypeGroup,
    RecognizeRequest,
    TaskStage,
    TaskStatus,
    TypeResult,
)
from ocr_rel.ocr.service import get_ocr_engine
from ocr_rel.pdf.converter import detect_file_format_label, document_to_images
from ocr_rel.services.audit_report_ocr import recognize_audit_report_detail
from ocr_rel.services.business_license_ocr import recognize_business_license_detail
from ocr_rel.services.capital_verification_ocr import recognize_capital_verification_detail
from ocr_rel.services.document_validator import DocumentTypeMismatchError, validate_document_type
from ocr_rel.services.extraction_service import extraction_service
from ocr_rel.services.grade_protection_ocr import recognize_grade_protection_detail
from ocr_rel.services.local_file_store import local_file_store
from ocr_rel.services.software_copyright_ocr import recognize_software_copyright_detail
from ocr_rel.services.upload_validation import validate_upload_size
from ocr_rel.services.task_manager import task_manager

logger = get_logger(__name__)

FileDownloadFn = Callable[[str], Awaitable[tuple[str, bytes]]]


class RecognitionService:
    def __init__(self) -> None:
        self._file_client = PlatformFileClient()
        self._callback_client = PlatformCallbackClient()

    @staticmethod
    def _finalize_detail(
        detail: dict[str, Any],
        doc_type: int,
        personnel: str | None,
    ) -> dict[str, Any]:
        if personnel and doc_type in {5, 9, 10}:
            merged = dict(detail)
            merged["personnel"] = personnel
            return merged
        return detail

    async def process_recognize_request(
        self,
        task_id: str,
        request: RecognizeRequest,
        *,
        ocr_engine: str | None = None,
    ) -> None:
        log_step(
            logger,
            task_id=task_id,
            registration_id=request.registrationId,
            step="recognize.accepted",
            message="收到生产识别请求",
            fileGroups=len(request.files),
        )
        await task_manager.mark_running(task_id)
        try:
            payload = await self._build_callback_payload(
                task_id=task_id,
                registration_id=request.registrationId,
                file_groups=request.files,
                ocr_engine=ocr_engine,
                download_file=self._file_client.download_file,
            )
            await task_manager.update_progress(
                task_id,
                stage=TaskStage.CALLBACK,
                progress=95,
                message="准备回调注册平台",
            )
            log_step(
                logger,
                task_id=task_id,
                registration_id=request.registrationId,
                step="callback.start",
                message="开始回调注册平台",
            )
            await self._callback_client.send_callback(payload)
            await task_manager.mark_success(task_id, payload)
            log_result(
                logger,
                task_id=task_id,
                registration_id=request.registrationId,
                result=payload.model_dump(),
            )
        except Exception as exc:
            logger.exception("Recognition task failed taskId=%s", task_id)
            log_step(
                logger,
                task_id=task_id,
                registration_id=request.registrationId,
                step="recognize.failed",
                message=str(exc),
            )
            await task_manager.mark_failed(task_id, str(exc))

    async def process_test_recognize_request(
        self,
        task_id: str,
        request: RecognizeRequest,
        *,
        ocr_engine: str | None = None,
        download_file: FileDownloadFn,
    ) -> None:
        log_step(
            logger,
            task_id=task_id,
            registration_id=request.registrationId,
            step="test.recognize.accepted",
            message="收到测试识别请求（模拟业务侧调用）",
            fileGroups=len(request.files),
        )
        await task_manager.mark_running(task_id)
        try:
            payload = await self._build_callback_payload(
                task_id=task_id,
                registration_id=request.registrationId,
                file_groups=request.files,
                ocr_engine=ocr_engine,
                download_file=download_file,
                callback_enabled=False,
            )
            await task_manager.mark_success(task_id, payload)
            log_result(
                logger,
                task_id=task_id,
                registration_id=request.registrationId,
                result=payload.model_dump(),
            )
        except Exception as exc:
            logger.exception("Test recognition task failed taskId=%s", task_id)
            log_step(
                logger,
                task_id=task_id,
                registration_id=request.registrationId,
                step="test.recognize.failed",
                message=str(exc),
            )
            await task_manager.mark_failed(task_id, str(exc))

    async def process_local_file(
        self,
        task_id: str,
        *,
        registration_id: str,
        doc_type: int,
        file_bytes: bytes,
        filename: str | None = None,
        ocr_engine: str | None = None,
        personnel: str | None = None,
    ) -> None:
        await task_manager.mark_running(task_id)
        try:
            detail = await self._recognize_document(
                task_id=task_id,
                registration_id=registration_id,
                file_bytes=file_bytes,
                doc_type=doc_type,
                filename=filename,
                ocr_engine=ocr_engine,
                personnel=personnel,
            )
            payload = CallbackPayload(
                registrationId=registration_id,
                results=[
                    TypeResult(
                        type=doc_type,
                        name=ATTACHMENT_TYPE_NAMES.get(doc_type, f"type-{doc_type}"),
                        detail=[detail],
                    )
                ],
            )
            await task_manager.mark_success(task_id, payload)
            log_result(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                result=payload.model_dump(),
            )
        except Exception as exc:
            logger.exception("Local parse task failed taskId=%s", task_id)
            await task_manager.mark_failed(task_id, str(exc))

    async def _build_callback_payload(
        self,
        *,
        task_id: str,
        registration_id: str,
        file_groups: list[FileTypeGroup],
        ocr_engine: str | None,
        download_file: FileDownloadFn,
        callback_enabled: bool = True,
    ) -> CallbackPayload:
        results: list[TypeResult] = []

        for group in file_groups:
            details: list[dict[str, Any]] = []
            for file_ref in group.files:
                await task_manager.update_progress(
                    task_id,
                    stage=TaskStage.DOWNLOADING,
                    progress=20,
                    message=f"下载附件 uuid={file_ref.uuid} type={group.type}",
                )
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="file.download",
                    message="开始下载附件",
                    uuid=file_ref.uuid,
                    type=group.type,
                )
                file_name, file_bytes = await download_file(file_ref.uuid)
                validate_upload_size(file_bytes, filename=file_name)
                await local_file_store.save(
                    task_id,
                    file_name=file_name,
                    content=file_bytes,
                )
                await task_manager.update_file_metadata(
                    task_id,
                    doc_type=group.type,
                    doc_type_name=group.name or ATTACHMENT_TYPE_NAMES.get(group.type),
                    file_size=len(file_bytes),
                    file_format=detect_file_format_label(file_bytes, file_name),
                    file_name=file_name,
                )
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="file.download.done",
                    message="附件下载完成",
                    uuid=file_ref.uuid,
                    fileName=file_name,
                    size=len(file_bytes),
                )

                detail = await self._recognize_document(
                    task_id=task_id,
                    registration_id=registration_id,
                    file_bytes=file_bytes,
                    doc_type=group.type,
                    filename=file_name,
                    ocr_engine=ocr_engine,
                    personnel=file_ref.personnel,
                    attachment_name=group.name,
                )
                if group.type in {5, 9, 10} and file_ref.personnel:
                    detail["personnel"] = file_ref.personnel
                details.append(detail)

            results.append(
                TypeResult(
                    type=group.type,
                    name=group.name or ATTACHMENT_TYPE_NAMES.get(group.type, f"type-{group.type}"),
                    detail=details,
                )
            )

        if callback_enabled:
            await task_manager.update_progress(
                task_id,
                stage=TaskStage.EXTRACTING,
                progress=85,
                message="结构化抽取完成，等待回调",
            )

        return CallbackPayload(registrationId=registration_id, results=results)

    async def _recognize_document(
        self,
        *,
        task_id: str | None = None,
        registration_id: str | None = None,
        file_bytes: bytes,
        doc_type: int,
        filename: str | None = None,
        ocr_engine: str | None = None,
        personnel: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        if task_id:
            await task_manager.update_progress(
                task_id,
                stage=TaskStage.OCR,
                progress=40,
                message=f"OCR 识别中 type={doc_type}",
            )
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="ocr.start",
            message="开始 OCR 识别",
            docType=doc_type,
            fileName=filename or "",
            engine=ocr_engine or "default",
        )

        images = document_to_images(file_bytes, doc_type=doc_type, filename=filename)
        engine = get_ocr_engine(ocr_engine)

        if doc_type == 3:
            detail, validation_text = await recognize_audit_report_detail(
                engine,
                images,
                task_id=task_id,
                registration_id=registration_id,
            )
            if not validation_text.strip():
                raise ValueError("OCR returned empty text")

            log_ocr_text(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                doc_type=doc_type,
                text=validation_text,
            )

            try:
                validate_document_type(doc_type, validation_text)
            except DocumentTypeMismatchError:
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="validate.type.failed",
                    message="文件内容与声明类型不一致",
                    docType=doc_type,
                )
                raise

            preview = validation_text[:500] + ("..." if len(validation_text) > 500 else "")
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="ocr.done",
                message="审计报告分页 OCR 完成",
                docType=doc_type,
                textLength=len(validation_text),
                totalPages=len(images),
            )
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="extract.done",
                message="审计报告抽取完成",
                docType=doc_type,
                detail=detail,
            )
            return self._finalize_detail(detail, doc_type, personnel)

        if doc_type == 4:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="recognize.type4.start",
                message="进入验资报告专用流程（仅首页 OCR+抽取，不扫描后续页）",
                docType=doc_type,
                renderedPages=len(images),
            )
            detail, validation_text = await recognize_capital_verification_detail(
                engine,
                images,
                task_id=task_id,
                registration_id=registration_id,
            )
            if not validation_text.strip():
                raise ValueError("OCR returned empty text")

            log_ocr_text(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                doc_type=doc_type,
                text=validation_text,
            )

            try:
                validate_document_type(doc_type, validation_text)
            except DocumentTypeMismatchError:
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="validate.type.failed",
                    message="文件内容与声明类型不一致",
                    docType=doc_type,
                )
                raise

            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="ocr.done",
                message="验资报告首页 OCR 完成",
                docType=doc_type,
                textLength=len(validation_text),
                totalPages=len(images),
            )
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="extract.done",
                message="验资报告抽取完成",
                docType=doc_type,
                detail=detail,
            )
            return self._finalize_detail(detail, doc_type, personnel)

        if doc_type == 1:
            detail, text = await recognize_business_license_detail(
                engine,
                images,
                task_id=task_id,
                registration_id=registration_id,
            )
            if not text.strip():
                raise ValueError("OCR returned empty text")

            log_ocr_text(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                doc_type=doc_type,
                text=text,
            )

            try:
                validate_document_type(doc_type, text)
            except DocumentTypeMismatchError:
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="validate.type.failed",
                    message="文件内容与声明类型不一致",
                    docType=doc_type,
                )
                raise

            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="ocr.done",
                message="营业执照 OCR 与结构化抽取完成",
                docType=doc_type,
                textLength=len(text),
            )
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="extract.done",
                message="营业执照抽取完成",
                docType=doc_type,
                detail=detail,
            )
            return self._finalize_detail(detail, doc_type, personnel)

        if doc_type == 6:
            cover_images = document_to_images(
                file_bytes,
                doc_type=doc_type,
                filename=filename,
                max_pages=1,
            )
            cover_text = (await engine.recognize_images(cover_images)).strip()
            if not cover_text:
                raise ValueError("OCR returned empty text on type-6 cover page")

            from ocr_rel.parsers.type6_grade_protection import detect_type6_document_kind

            document_kind = detect_type6_document_kind(cover_text)
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="recognize.type6.start",
                message="type6 分流识别：软著仅首页，等保全文 OCR",
                docType=doc_type,
                documentKind=document_kind,
            )

            if document_kind == "software_copyright":
                detail, text = await recognize_software_copyright_detail(
                    engine,
                    cover_images,
                    cover_text=cover_text,
                    task_id=task_id,
                    registration_id=registration_id,
                )
            else:
                full_images = document_to_images(
                    file_bytes,
                    doc_type=doc_type,
                    filename=filename,
                    max_pages=None,
                )
                detail, text = await recognize_grade_protection_detail(
                    engine,
                    full_images,
                    task_id=task_id,
                    registration_id=registration_id,
                )

            log_ocr_text(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                doc_type=doc_type,
                text=text,
            )

            try:
                validate_document_type(doc_type, text)
            except DocumentTypeMismatchError:
                log_step(
                    logger,
                    task_id=task_id,
                    registration_id=registration_id,
                    step="validate.type.failed",
                    message="文件内容与声明类型不一致",
                    docType=doc_type,
                )
                raise

            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="ocr.done",
                message="type6 识别完成",
                docType=doc_type,
                documentKind=document_kind if document_kind != "unknown" else detect_type6_document_kind(text),
                textLength=len(text),
            )
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="extract.done",
                message="type6 结构化抽取完成",
                docType=doc_type,
                detail=detail,
            )
            return self._finalize_detail(detail, doc_type, personnel)

        if doc_type == 5:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="recognize.type5.start",
                message="从业人员身份证识别",
                docType=doc_type,
                personnel=personnel or "",
            )
        elif doc_type == 7:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="recognize.type7.start",
                message="法人征信报告识别",
                docType=doc_type,
            )
        elif doc_type in {8, 9, 10, 11}:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step=f"recognize.type{doc_type}.start",
                message="信用证明识别",
                docType=doc_type,
                personnel=personnel or "",
            )

        text = await engine.recognize_images(images)
        if not text.strip():
            raise ValueError("OCR returned empty text")

        log_ocr_text(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            doc_type=doc_type,
            text=text,
        )

        try:
            validate_document_type(doc_type, text)
        except DocumentTypeMismatchError:
            log_step(
                logger,
                task_id=task_id,
                registration_id=registration_id,
                step="validate.type.failed",
                message="文件内容与声明类型不一致",
                docType=doc_type,
            )
            raise

        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="ocr.done",
            message="OCR 识别完成",
            docType=doc_type,
            textLength=len(text),
        )

        if task_id:
            await task_manager.update_progress(
                task_id,
                stage=TaskStage.EXTRACTING,
                progress=70,
                message=f"结构化抽取中 type={doc_type}",
            )
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="extract.start",
            message="开始结构化抽取",
            docType=doc_type,
        )

        detail = await extraction_service.extract(
            doc_type,
            text,
            personnel=personnel,
            attachment_name=attachment_name,
            task_id=task_id,
            registration_id=registration_id,
        )
        log_step(
            logger,
            task_id=task_id,
            registration_id=registration_id,
            step="extract.done",
            message="结构化抽取完成",
            docType=doc_type,
            detail=detail,
        )
        return self._finalize_detail(detail, doc_type, personnel)


recognition_service = RecognitionService()
