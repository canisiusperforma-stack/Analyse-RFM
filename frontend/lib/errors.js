import axios from "axios";

const MESSAGES = {
  NETWORK:
    "Impossible de contacter le serveur. Vérifiez votre connexion Internet.",
  TIMEOUT:
    "Le serveur met trop de temps à répondre. Veuillez réessayer plus tard.",
  UNAUTHORIZED: "Session expirée. Veuillez vous reconnecter.",
  FORBIDDEN: "Vous n'avez pas les droits nécessaires.",
  NOT_FOUND: "La ressource demandée est introuvable.",
  VALIDATION: "Le formulaire contient des erreurs de validation.",
  SERVER: "Une erreur interne est survenue sur le serveur.",
  UNKNOWN: "Une erreur inattendue est survenue.",
};

function backendMessage(payload) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail) && payload.detail.length > 0) {
    return payload.detail.map((d) => d.msg || d.message || String(d)).join(". ");
  }
  if (typeof payload?.message === "string") return payload.message;
  return null;
}

export class ApiError extends Error {
  constructor(
    message,
    { status = 0, code = "API_ERROR", detail = null, fieldErrors = null } = {}
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

export function normalizeApiError(error) {
  if (error instanceof ApiError) return error;

  if (axios.isAxiosError(error)) {
    const { response, code, message } = error;
    const status = response?.status ?? 0;

    if (code === "ERR_NETWORK") {
      return new ApiError(MESSAGES.NETWORK, { status, code: "NETWORK" });
    }
    if (code === "ECONNABORTED") {
      return new ApiError(MESSAGES.TIMEOUT, { status, code: "TIMEOUT" });
    }

    const detail = response?.data ? backendMessage(response.data) : null;
    let msg = "";
    let errCode = "";

    if (status === 401) {
      msg = MESSAGES.UNAUTHORIZED;
      errCode = "UNAUTHORIZED";
    } else if (status === 403) {
      msg = MESSAGES.FORBIDDEN;
      errCode = "FORBIDDEN";
    } else if (status === 404) {
      msg = MESSAGES.NOT_FOUND;
      errCode = "NOT_FOUND";
    } else if (status === 422) {
      msg = detail || MESSAGES.VALIDATION;
      errCode = "VALIDATION";
    } else if (status >= 500) {
      msg = MESSAGES.SERVER;
      errCode = "SERVER";
    } else {
      msg = detail || message;
      errCode = status > 0 ? `HTTP_${status}` : "UNKNOWN";
    }

    return new ApiError(msg, { status, code: errCode, detail });
  }

  return new ApiError(error?.message || MESSAGES.UNKNOWN, {
    code: "UNKNOWN",
  });
}

export function getApiErrorText(error) {
  if (error instanceof ApiError) return error.message;
  return error?.message || MESSAGES.UNKNOWN;
}