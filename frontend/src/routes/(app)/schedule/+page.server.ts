import { fail } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { BotSettings } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

function token(cookies: { get: (name: string) => string | undefined }): string | undefined {
	return cookies.get(PANEL_TOKEN_COOKIE);
}

function toFailure(error: unknown) {
	if (error instanceof ApiError) {
		return fail(error.status, { message: error.message });
	}
	throw error;
}

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	try {
		const settings = await apiFetch<BotSettings>('/api/settings', {
			token: token(cookies),
			fetch
		});
		return { settings, loadError: null };
	} catch (error) {
		if (error instanceof ApiError) {
			return { settings: null, loadError: error.message };
		}
		throw error;
	}
};

export const actions: Actions = {
	schedule: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const weekdays = form.getAll('weekdays').map((value) => Number(value));

		try {
			await apiFetch<BotSettings>('/api/settings', {
				token: token(cookies),
				method: 'PATCH',
				body: {
					schedule: {
						window_start: Number(form.get('window_start') ?? 9),
						window_end: Number(form.get('window_end') ?? 21),
						weekdays_enabled: weekdays
					}
				},
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Расписание сохранено' };
	},

	limits: async ({ request, cookies, fetch }) => {
		const form = await request.formData();

		try {
			await apiFetch<BotSettings>('/api/settings', {
				token: token(cookies),
				method: 'PATCH',
				body: {
					limits: {
						delay_min_minutes: Number(form.get('delay_min_minutes') ?? 5),
						delay_max_minutes: Number(form.get('delay_max_minutes') ?? 15),
						account_rotation_size: Number(form.get('account_rotation_size') ?? 3)
					}
				},
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Лимиты сохранены' };
	},

	pause: async ({ request, cookies, fetch }) => {
		const form = await request.formData();

		try {
			await apiFetch<BotSettings>('/api/settings', {
				token: token(cookies),
				method: 'PATCH',
				body: { schedule: { paused: form.get('paused') === 'true' } },
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: form.get('paused') === 'true' ? 'Бот на паузе' : 'Бот запущен' };
	}
};
