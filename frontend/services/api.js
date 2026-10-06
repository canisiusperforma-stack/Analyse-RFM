import axios from "axios";
import { normalizeApiError } from "@/lib/errors";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "/api",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("rfm_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  // Le Content-Type par défaut est inerte pour un JSON mais ruineux pour un
  // envoi multipart : `transformRequest` d'axios sérialise alors le FormData
  // en JSON au lieu de le laisser tel quel, et le backend répond 422 en
  // attendant `multipart/form-data`. On retire l'en-tête pour laisser le
  // navigateur le poser lui-même, avec sa frontière.
  if (
    typeof FormData !== "undefined" &&
    config.data instanceof FormData
  ) {
    if (typeof config.headers?.delete === "function") {
      config.headers.delete("Content-Type");
    } else {
      delete config.headers["Content-Type"];
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error?.response?.status === 401 &&
      typeof window !== "undefined"
    ) {
      const url = error.config?.url || "";
      const estTentativeConnexion = /\/auth\/(connexion|inscription)/.test(url);
      if (
        !estTentativeConnexion &&
        window.localStorage.getItem("rfm_token")
      ) {
        window.dispatchEvent(new Event("auth:expired"));
      }
    }
    return Promise.reject(normalizeApiError(error));
  }
);

export default api;