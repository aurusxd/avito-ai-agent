import { json } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { ProxyIssueResult } from '$lib/types';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, cookies, fetch }) => {
	try {
		const issued = await apiFetch<ProxyIssueResult>('/api/accounts/proxy/issue', {
			token: cookies.get(PANEL_TOKEN_COOKIE),
			method: 'POST',
			body: await request.json(),
			fetch
		});
		return json(issued);
	} catch (error) {
		if (error instanceof ApiError) {
			return json({ message: error.message }, { status: error.status });
		}
		throw error;
	}
};
