import { fail, redirect } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

function safeRedirectTarget(value: FormDataEntryValue | null): string {
	const target = typeof value === 'string' ? value : '';
	return target.startsWith('/') && !target.startsWith('//') ? target : '/dashboard';
}

export const load: PageServerLoad = ({ cookies, url }) => {
	if (cookies.get(PANEL_TOKEN_COOKIE)) {
		redirect(303, safeRedirectTarget(url.searchParams.get('redirectTo')));
	}
	return { redirectTo: url.searchParams.get('redirectTo') ?? '/dashboard' };
};

export const actions: Actions = {
	default: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const token = String(form.get('token') ?? '').trim();
		const redirectTo = safeRedirectTarget(form.get('redirectTo'));

		if (!token) {
			return fail(400, { message: 'Введите токен панели' });
		}

		try {
			await apiFetch('/api/categories', { token, fetch });
		} catch (error) {
			if (error instanceof ApiError && error.status === 401) {
				return fail(401, { message: 'Неверный токен панели' });
			}
			if (error instanceof ApiError) {
				return fail(error.status, { message: error.message });
			}
			throw error;
		}

		cookies.set(PANEL_TOKEN_COOKIE, token, {
			path: '/',
			httpOnly: true,
			sameSite: 'lax',
			maxAge: 60 * 60 * 12
		});

		redirect(303, redirectTo);
	}
};
