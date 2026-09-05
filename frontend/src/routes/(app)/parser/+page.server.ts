import { fail } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { Category, ParserRunResult, Seller } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ cookies, fetch, url }) => {
	const token = cookies.get(PANEL_TOKEN_COOKIE);
	const selected = url.searchParams.get('category_id');
	const categoryId = selected ? Number(selected) : null;

	const sellersPath =
		categoryId === null ? '/api/parser/sellers' : `/api/parser/sellers?category_id=${categoryId}`;

	try {
		const [categories, sellers] = await Promise.all([
			apiFetch<Category[]>('/api/categories', { token, fetch }),
			apiFetch<Seller[]>(sellersPath, { token, fetch })
		]);
		return { categories, sellers, categoryId, loadError: null };
	} catch (error) {
		if (error instanceof ApiError) {
			return {
				categories: [] as Category[],
				sellers: [] as Seller[],
				categoryId,
				loadError: error.message
			};
		}
		throw error;
	}
};

export const actions: Actions = {
	run: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const categoryId = Number(form.get('category_id'));

		if (!Number.isInteger(categoryId) || categoryId <= 0) {
			return fail(400, { message: 'Выберите категорию' });
		}

		try {
			const result = await apiFetch<ParserRunResult>(
				`/api/parser/categories/${categoryId}/run`,
				{ token: cookies.get(PANEL_TOKEN_COOKIE), method: 'POST', fetch }
			);
			return {
				message:
					`Продавцов подошло: ${result.sellers_matched}, ` +
					`новых: ${result.sellers_created}, объявлений добавлено: ${result.listings_created}`
			};
		} catch (error) {
			if (error instanceof ApiError) {
				return fail(error.status, { message: error.message });
			}
			throw error;
		}
	}
};
