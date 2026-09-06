import { json } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { LoginSession } from '$lib/types';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, cookies, fetch }) => {
	try {
		const session = await apiFetch<LoginSession>('/api/accounts/login/' + params.id, {
			token: cookies.get(PANEL_TOKEN_COOKIE),
			fetch
		});
		return json(session);
	} catch (error) {
		if (error instanceof ApiError) {
			return json({ message: error.message }, { status: error.status });
		}
		throw error;
	}
};

export const DELETE: RequestHandler = async ({ params, cookies, fetch }) => {
	try {
		const session = await apiFetch<LoginSession>(
			'/api/accounts/login/' + params.id + '/cancel',
			{ token: cookies.get(PANEL_TOKEN_COOKIE), method: 'POST', fetch }
		);
		return json(session);
	} catch (error) {
		if (error instanceof ApiError) {
			return json({ message: error.message }, { status: error.status });
		}
		throw error;
	}
};
