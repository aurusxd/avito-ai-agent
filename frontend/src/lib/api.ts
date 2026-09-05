import { env } from '$env/dynamic/private';
import type { ApiErrorBody } from '$lib/types';

export const PANEL_TOKEN_COOKIE = 'panel_token';
export const PANEL_TOKEN_HEADER = 'X-Panel-Token';

export function apiBaseUrl(): string {
	return env.API_BASE_URL ?? 'http://127.0.0.1:8000';
}

export class ApiError extends Error {
	constructor(
		readonly status: number,
		readonly code: string,
		message: string,
		readonly details?: unknown
	) {
		super(message);
		this.name = 'ApiError';
	}
}

type RequestOptions = {
	token?: string;
	method?: string;
	body?: unknown;
	fetch?: typeof globalThis.fetch;
};

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
	const { token, method = 'GET', body, fetch: fetchImpl = globalThis.fetch } = options;

	const headers: Record<string, string> = { Accept: 'application/json' };
	if (token) headers[PANEL_TOKEN_HEADER] = token;
	if (body !== undefined) headers['Content-Type'] = 'application/json';

	let response: Response;
	try {
		response = await fetchImpl(apiBaseUrl() + path, {
			method,
			headers,
			body: body === undefined ? undefined : JSON.stringify(body)
		});
	} catch (cause) {
		throw new ApiError(503, 'api_unreachable', 'Бэкенд недоступен', cause);
	}

	if (response.status === 204) return undefined as T;

	const text = await response.text();
	const payload: unknown = text ? JSON.parse(text) : null;

	if (!response.ok) {
		const error = (payload as ApiErrorBody | null)?.error;
		throw new ApiError(
			response.status,
			error?.code ?? 'unknown_error',
			error?.message ?? 'Запрос завершился ошибкой',
			error?.details
		);
	}

	return payload as T;
}
