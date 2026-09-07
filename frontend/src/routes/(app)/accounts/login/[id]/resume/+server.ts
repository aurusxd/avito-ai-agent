import { json } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { LoginSession } from '$lib/types';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ params, cookies, fetch }) => {
	try {
		const session = await apiFetch<LoginSession>(
			'/api/accounts/login/' + params.id + '/resume',
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
