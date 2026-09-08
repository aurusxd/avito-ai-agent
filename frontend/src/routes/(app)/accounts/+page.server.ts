import { fail } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type {
	Account,
	AccountCreate,
	AccountUpdate,
	ProxyBalance,
	RotationPreview
} from '$lib/types';
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
		const [accounts, rotation] = await Promise.all([
			apiFetch<Account[]>('/api/accounts', { token: token(cookies), fetch }),
			apiFetch<RotationPreview>('/api/accounts/rotation', { token: token(cookies), fetch })
		]);
		// the provider can be down without breaking the page
		const proxyBalances = await apiFetch<ProxyBalance[]>('/api/accounts/proxy/balances', {
			token: token(cookies),
			fetch
		}).catch(() => [] as ProxyBalance[]);
		return { accounts, rotation, proxyBalances, loadError: null };
	} catch (error) {
		if (error instanceof ApiError) {
			return {
				accounts: [] as Account[],
				rotation: null,
				proxyBalances: [] as ProxyBalance[],
				loadError: error.message
			};
		}
		throw error;
	}
};

export const actions: Actions = {
	create: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const payload: AccountCreate = {
			login: String(form.get('login') ?? '').trim(),
			session_storage_path: String(form.get('session_storage_path') ?? '').trim(),
			daily_limit: Number(form.get('daily_limit') ?? 15)
		};

		if (!payload.login || !payload.session_storage_path) {
			return fail(400, { message: 'Заполните логин и путь к файлу сессии' });
		}

		try {
			await apiFetch<Account>('/api/accounts', {
				token: token(cookies),
				method: 'POST',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Аккаунт добавлен' };
	},

	toggle: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const payload: AccountUpdate = {
			status: form.get('status') === 'active' ? 'active' : 'paused'
		};

		try {
			await apiFetch<Account>('/api/accounts/' + id, {
				token: token(cookies),
				method: 'PATCH',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Статус аккаунта обновлён' };
	},

	limit: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const payload: AccountUpdate = { daily_limit: Number(form.get('daily_limit') ?? 15) };

		try {
			await apiFetch<Account>('/api/accounts/' + id, {
				token: token(cookies),
				method: 'PATCH',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Суточный лимит обновлён' };
	},

	remove: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));

		try {
			await apiFetch<void>('/api/accounts/' + id, {
				token: token(cookies),
				method: 'DELETE',
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Аккаунт удалён' };
	}
};
