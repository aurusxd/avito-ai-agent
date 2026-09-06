<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { Badge } from '$lib/ui/badge/index.js';
	import { Button } from '$lib/ui/button/index.js';
	import * as Dialog from '$lib/ui/dialog/index.js';
	import { Input } from '$lib/ui/input/index.js';
	import { Label } from '$lib/ui/label/index.js';
	import type { LoginSession, LoginStatus } from '$lib/types';

	let open = $state(false);
	let session: LoginSession | null = $state(null);
	let errorMessage: string | null = $state(null);
	let busy = $state(false);
	let code = $state('');
	let poller: ReturnType<typeof setInterval> | null = null;

	const TERMINAL: LoginStatus[] = ['done', 'failed', 'expired'];

	const statusLabel: Record<LoginStatus, string> = {
		starting: 'открываем браузер',
		code_required: 'ждём код из СМС',
		captcha_required: 'нужна проверка человеком',
		saving: 'сохраняем сессию',
		done: 'готово',
		failed: 'не получилось',
		expired: 'время вышло'
	};

	function stopPolling() {
		if (poller) {
			clearInterval(poller);
			poller = null;
		}
	}

	function startPolling(id: string) {
		stopPolling();
		poller = setInterval(async () => {
			const response = await fetch(`/accounts/login/${id}`);
			if (!response.ok) return;
			applySession(await response.json());
		}, 3000);
	}

	function applySession(next: LoginSession) {
		session = next;
		if (!TERMINAL.includes(next.status)) return;

		stopPolling();
		if (next.status === 'done') {
			toast.success(`Аккаунт ${next.login} добавлен`);
			invalidateAll();
			reset();
			open = false;
		}
	}

	function reset() {
		session = null;
		errorMessage = null;
		code = '';
		busy = false;
	}

	async function send(url: string, body?: unknown) {
		busy = true;
		errorMessage = null;
		try {
			const response = await fetch(url, {
				method: 'POST',
				headers: body ? { 'Content-Type': 'application/json' } : undefined,
				body: body ? JSON.stringify(body) : undefined
			});
			const payload = await response.json();
			if (!response.ok) {
				errorMessage = payload.message ?? 'Запрос не прошёл';
				return null;
			}
			return payload as LoginSession;
		} catch {
			errorMessage = 'Панель не смогла достучаться до бэкенда';
			return null;
		} finally {
			busy = false;
		}
	}

	async function submitCredentials(event: SubmitEvent) {
		event.preventDefault();
		const form = new FormData(event.currentTarget as HTMLFormElement);
		const proxy = String(form.get('proxy_url') ?? '').trim();

		const next = await send('/accounts/login', {
			login: String(form.get('login') ?? '').trim(),
			password: String(form.get('password') ?? ''),
			proxy_url: proxy || null,
			daily_limit: Number(form.get('daily_limit') ?? 15)
		});

		if (next) {
			applySession(next);
			if (!TERMINAL.includes(next.status)) startPolling(next.session_id);
		}
	}

	async function submitCode(event: SubmitEvent) {
		event.preventDefault();
		if (!session) return;

		const next = await send(`/accounts/login/${session.session_id}/code`, { code: code.trim() });
		if (next) {
			code = '';
			applySession(next);
		}
	}

	async function cancel() {
		if (session && !TERMINAL.includes(session.status)) {
			await fetch(`/accounts/login/${session.session_id}`, { method: 'DELETE' });
		}
		stopPolling();
		reset();
		open = false;
	}

	$effect(() => {
		if (!open) stopPolling();
		return stopPolling;
	});
</script>

<Dialog.Root bind:open onOpenChange={(value) => (value ? reset() : cancel())}>
	<Dialog.Trigger>
		{#snippet child({ props })}
			<Button {...props}>Войти в аккаунт</Button>
		{/snippet}
	</Dialog.Trigger>
	<Dialog.Content class="sm:max-w-lg">
		<Dialog.Header>
			<Dialog.Title>Вход в аккаунт Авито</Dialog.Title>
			<Dialog.Description>
				Бот откроет браузер, войдёт под этими данными и сохранит сессию. Пароль нигде не
				сохраняется.
			</Dialog.Description>
		</Dialog.Header>

		{#if !session}
			<form class="space-y-4" onsubmit={submitCredentials}>
				<div class="space-y-2">
					<Label for="login-field">Телефон или почта</Label>
					<Input id="login-field" name="login" autocomplete="off" required />
				</div>
				<div class="space-y-2">
					<Label for="password-field">Пароль</Label>
					<Input
						id="password-field"
						name="password"
						type="password"
						autocomplete="off"
						required
					/>
				</div>
				<div class="space-y-2">
					<Label for="proxy-field">Прокси аккаунта</Label>
					<Input
						id="proxy-field"
						name="proxy_url"
						placeholder="http://user:pass@host:port"
						autocomplete="off"
					/>
					<p class="text-muted-foreground text-xs">
						Вход должен идти через тот же прокси, на котором аккаунт будет работать.
					</p>
				</div>
				<div class="space-y-2">
					<Label for="limit-field">Суточный лимит</Label>
					<Input
						id="limit-field"
						name="daily_limit"
						type="number"
						min="1"
						max="15"
						value="15"
						required
					/>
				</div>
				{#if errorMessage}
					<p class="text-destructive text-sm" role="alert">{errorMessage}</p>
				{/if}
				<Dialog.Footer>
					<Button type="submit" disabled={busy}>
						{busy ? 'Запускаем...' : 'Войти'}
					</Button>
				</Dialog.Footer>
			</form>
		{:else}
			<div class="space-y-4">
				<div class="flex items-center gap-2">
					<Badge
						variant={session.status === 'failed' || session.status === 'expired'
							? 'destructive'
							: 'secondary'}
					>
						{statusLabel[session.status]}
					</Badge>
					<span class="text-muted-foreground text-sm">{session.login}</span>
				</div>

				{#if session.hint}
					<p class="text-sm">{session.hint}</p>
				{/if}

				{#if session.status === 'code_required'}
					<form class="space-y-3" onsubmit={submitCode}>
						<div class="space-y-2">
							<Label for="code-field">Код из СМС</Label>
							<Input
								id="code-field"
								bind:value={code}
								inputmode="numeric"
								autocomplete="off"
								required
							/>
						</div>
						{#if errorMessage}
							<p class="text-destructive text-sm" role="alert">{errorMessage}</p>
						{/if}
						<Button type="submit" disabled={busy}>
							{busy ? 'Проверяем...' : 'Подтвердить'}
						</Button>
					</form>
				{:else if session.status === 'captcha_required'}
					<div class="space-y-3">
						<p class="text-sm">
							Авито показал проверку. Автоматически она не проходится, нужен человек за
							браузером на сервере.
						</p>
						{#if session.has_screenshot}
							<img
								src={`/accounts/login/${session.session_id}/screenshot`}
								alt="Что показывает Авито"
								class="border-border w-full rounded-md border"
							/>
						{/if}
					</div>
				{:else if session.status === 'starting' || session.status === 'saving'}
					<p class="text-muted-foreground text-sm">Идёт вход, это занимает до минуты.</p>
				{/if}

				<Dialog.Footer>
					{#if session.status === 'failed' || session.status === 'expired'}
						<Button variant="outline" onclick={reset}>Попробовать снова</Button>
					{/if}
					<Button variant="ghost" onclick={cancel}>Закрыть</Button>
				</Dialog.Footer>
			</div>
		{/if}
	</Dialog.Content>
</Dialog.Root>
