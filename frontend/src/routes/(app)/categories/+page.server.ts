import { fail } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { Category, CategoryCreate, CategoryUpdate } from '$lib/types';
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
		const categories = await apiFetch<Category[]>('/api/categories', {
			token: token(cookies),
			fetch
		});
		return { categories, loadError: null };
	} catch (error) {
		if (error instanceof ApiError) {
			return { categories: [] as Category[], loadError: error.message };
		}
		throw error;
	}
};

export const actions: Actions = {
	create: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const payload: CategoryCreate = {
			name: String(form.get('name') ?? '').trim(),
			avito_url_or_slug: String(form.get('avito_url_or_slug') ?? '').trim(),
			region: String(form.get('region') ?? '').trim(),
			min_listings_per_seller: Number(form.get('min_listings_per_seller') ?? 3),
			enabled: form.get('enabled') === 'on'
		};

		if (!payload.name || !payload.avito_url_or_slug || !payload.region) {
			return fail(400, { message: 'Заполните название, ссылку и регион' });
		}

		try {
			await apiFetch<Category>('/api/categories', {
				token: token(cookies),
				method: 'POST',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Категория создана' };
	},

	toggle: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const payload: CategoryUpdate = { enabled: form.get('enabled') === 'true' };

		try {
			await apiFetch<Category>('/api/categories/' + id, {
				token: token(cookies),
				method: 'PATCH',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Категория обновлена' };
	},

	remove: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));

		try {
			await apiFetch<void>('/api/categories/' + id, {
				token: token(cookies),
				method: 'DELETE',
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Категория удалена' };
	}
};
