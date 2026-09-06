import { fail } from '@sveltejs/kit';
import { ApiError, PANEL_TOKEN_COOKIE, apiFetch } from '$lib/api';
import type { Script, ScriptCreate, ScriptUpdate, StageCoverage } from '$lib/types';
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

function stageOf(value: FormDataEntryValue | null): 1 | 2 | 3 {
	const stage = Number(value);
	return stage === 2 || stage === 3 ? stage : 1;
}

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	try {
		const [scripts, coverage] = await Promise.all([
			apiFetch<Script[]>('/api/scripts', { token: token(cookies), fetch }),
			apiFetch<StageCoverage[]>('/api/scripts/coverage', { token: token(cookies), fetch })
		]);
		return { scripts, coverage, loadError: null };
	} catch (error) {
		if (error instanceof ApiError) {
			return { scripts: [] as Script[], coverage: [] as StageCoverage[], loadError: error.message };
		}
		throw error;
	}
};

export const actions: Actions = {
	create: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const payload: ScriptCreate = {
			stage: stageOf(form.get('stage')),
			variant_index: Number(form.get('variant_index') ?? 1),
			template_text: String(form.get('template_text') ?? '').trim(),
			active: form.get('active') === 'on'
		};

		if (!payload.template_text) {
			return fail(400, { message: 'Введите текст шаблона' });
		}

		try {
			await apiFetch<Script>('/api/scripts', {
				token: token(cookies),
				method: 'POST',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Вариант добавлен' };
	},

	save: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const payload: ScriptUpdate = {
			template_text: String(form.get('template_text') ?? '').trim()
		};

		try {
			await apiFetch<Script>('/api/scripts/' + id, {
				token: token(cookies),
				method: 'PATCH',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Шаблон сохранён' };
	},

	toggle: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const payload: ScriptUpdate = { active: form.get('active') === 'true' };

		try {
			await apiFetch<Script>('/api/scripts/' + id, {
				token: token(cookies),
				method: 'PATCH',
				body: payload,
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Вариант обновлён' };
	},

	remove: async ({ request, cookies, fetch }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));

		try {
			await apiFetch<void>('/api/scripts/' + id, {
				token: token(cookies),
				method: 'DELETE',
				fetch
			});
		} catch (error) {
			return toFailure(error);
		}

		return { message: 'Вариант удалён' };
	}
};
