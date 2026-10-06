from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        statut: int,
        code: str,
        message: str,
        detail: Optional[Any] = None,
    ) -> None:
        self.statut = statut
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        corps: Dict[str, Any] = {
            "statut": self.statut,
            "code": self.code,
            "message": self.message,
        }
        if self.detail is not None:
            corps["detail"] = self.detail
        return corps


class ErreurNotFound(ApiError):
    def __init__(self, message: str = "Ressource non trouvée") -> None:
        super().__init__(404, "NOT_FOUND", message)


class ErreurConflict(ApiError):
    def __init__(self, message: str = "Conflit de données") -> None:
        super().__init__(409, "CONFLICT", message)


class ErreurUnauthorized(ApiError):
    def __init__(self, message: str = "Authentification requise") -> None:
        super().__init__(401, "UNAUTHORIZED", message)


class ErreurForbidden(ApiError):
    def __init__(self, message: str = "Accès interdit") -> None:
        super().__init__(403, "FORBIDDEN", message)


class ErreurValidation(ApiError):
    def __init__(self, detail: Any) -> None:
        super().__init__(422, "VALIDATION_ERROR", "Données invalides", detail)


class ErreurInterne(ApiError):
    def __init__(self, message: str = "Erreur interne du serveur") -> None:
        super().__init__(500, "INTERNAL_ERROR", message)


class ErreurIndisponible(ApiError):
    def __init__(self, message: str = "Service indisponible") -> None:
        super().__init__(503, "SERVICE_UNAVAILABLE", message)


def _corps_erreur(
    statut: int,
    code: str,
    message: str,
    detail: Optional[Any] = None,
) -> Dict[str, Any]:
    corps: Dict[str, Any] = {
        "erreur": {
            "statut": statut,
            "code": code,
            "message": message,
        }
    }
    if detail is not None:
        corps["erreur"]["detail"] = detail
    return corps


def _json_safe(valeur: Any) -> Any:
    """Rend une valeur sans danger pour la sérialisation par `JSONResponse`.

    `RequestValidationError.errors()` restitue la cause brute d'une erreur de
    validation : pour un `value_error` — donc pour tout `ValueError` levé dans
    un `@model_validator` — le champ `ctx` contient l'instance d'exception
    elle-même. La renvoyer telle quelle fait échouer la sérialisation, et cet
    échec remplace un `422` par un `500` : l'appelant reçoit « erreur interne »
    au lieu du motif du refus, qui est précisément ce qu'il lui faut pour
    corriger sa requête.

    Un `ObjectId`, un `Decimal128`, un `datetime` ou n'importe quel objet
    place dans `input` posent le même problème. Tout ce qui n'est pas déjà un
    type JSON est donc ramené à sa représentation textuelle : le message
    d'erreur reste lisible, la réponse ne peut plus casser.
    """
    if valeur is None or isinstance(valeur, (bool, int, float, str)):
        return valeur
    if isinstance(valeur, dict):
        return {str(cle): _json_safe(item) for cle, item in valeur.items()}
    if isinstance(valeur, (list, tuple, set)):
        return [_json_safe(item) for item in valeur]
    return str(valeur)


def enregistrer_gestionnaires_erreurs(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def gerer_api_error(
        request: Request,
        exc: ApiError,
    ) -> JSONResponse:
        logger.warning(
            "ApiError %s (%s) sur %s %s",
            exc.statut,
            exc.code,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.statut,
            content=_corps_erreur(
                statut=exc.statut,
                code=exc.code,
                message=exc.message,
                detail=exc.detail,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def gerer_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        logger.warning(
            "HTTP %s sur %s %s",
            exc.status_code,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_corps_erreur(
                statut=exc.status_code,
                code="HTTP_ERROR",
                message=str(exc.detail),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def gerer_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "Validation échouée sur %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=422,
            content=_corps_erreur(
                statut=422,
                code="VALIDATION_ERROR",
                message="Données de requête invalides",
                detail=_json_safe(exc.errors()),
            ),
        )

    @app.exception_handler(Exception)
    async def gerer_erreur_generique(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Erreur non gérée sur %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        corps = _corps_erreur(
            statut=500,
            code="INTERNAL_ERROR",
            message="Erreur interne du serveur",
        )
        if settings.DEBUG:
            corps["erreur"]["detail"] = str(exc)
        return JSONResponse(status_code=500, content=corps)