import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { Category } from '$lib/types';
import type { PageServerLoad } from './$types';

type Health = {
	status: string;
	database: boolean;
	scheduler: boolean;
};

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	const token = cookies.get(PANEL_TOKEN_COOKIE);

	const health = await apiFetch<Health>('/health', { fetch }).catch(() => null);

	let categories: Category[] = [];
	let loadError: string | null = null;
	try {
		categories = await apiFetch<Category[]>('/api/categories', { token, fetch });
	} catch (error) {
		if (!(error instanceof ApiError)) throw error;
		loadError = error.message;
	}

	return { health, categories, loadError };
};
