import { fail } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { DashboardStats } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

type Health = {
	status: string;
	database: boolean;
	scheduler: boolean;
};

function token(cookies: { get: (name: string) => string | undefined }): string | undefined {
	return cookies.get(PANEL_TOKEN_COOKIE);
}

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	const health = await apiFetch<Health>('/health', { fetch }).catch(() => null);

	try {
		const stats = await apiFetch<DashboardStats>('/api/dashboard/stats', {
			token: token(cookies),
			fetch
		});
		return { health, stats, loadError: null };
	} catch (error) {
		if (error instanceof ApiError) {
			return { health, stats: null, loadError: error.message };
		}
		throw error;
	}
};

export const actions: Actions = {
	pause: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const paused = form.get('paused') === 'true';

		try {
			await apiFetch<unknown>('/api/settings', {
				token: token(cookies),
				method: 'PATCH',
				body: { schedule: { paused } },
				fetch
			});
		} catch (error) {
			if (error instanceof ApiError) {
				return fail(error.status, { message: error.message });
			}
			throw error;
		}

		return { message: paused ? 'Бот на паузе' : 'Бот запущен' };
	}
};
