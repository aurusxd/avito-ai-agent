import { error } from '@sveltejs/kit';
import { PANEL_TOKEN_COOKIE, apiBaseUrl } from '$lib/api';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, cookies, fetch }) => {
	const response = await fetch(apiBaseUrl() + '/api/accounts/login/' + params.id + '/screenshot', {
		headers: { 'X-Panel-Token': cookies.get(PANEL_TOKEN_COOKIE) ?? '' }
	});

	if (!response.ok) {
		error(response.status, 'Скриншот недоступен');
	}

	return new Response(await response.arrayBuffer(), {
		headers: { 'Content-Type': 'image/png', 'Cache-Control': 'no-store' }
	});
};
