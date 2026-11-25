from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError

_STATUS = {
    "validation_error": 422,
    "not_found": 404,
    "dataset_mismatch": 409,
    "idempotency_conflict": 409,
    "not_ready": 409,
    "adapter_rejected": 422,
    "run_failed": 500,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain(_request, exc: DomainError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
            status_code=_STATUS.get(exc.code, 400),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request, exc: RequestValidationError):
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
            status_code=422,
        )
