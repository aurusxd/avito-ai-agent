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
	let poller: ReturnType<typeof setInterval> | null = null;

	const TERMINAL: LoginStatus[] = ['done', 'failed', 'expired'];

	const statusLabel: Record<LoginStatus, string> = {
		starting: 'открываем браузер',
		waiting_for_operator: 'войдите в окне',
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
		}, 5000);
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

	async function openBrowser(event: SubmitEvent) {
		event.preventDefault();
		const form = new FormData(event.currentTarget as HTMLFormElement);
		const proxy = String(form.get('proxy_url') ?? '').trim();

		const next = await send('/accounts/login', {
			login: String(form.get('login') ?? '').trim(),
			proxy_url: proxy || null,
			daily_limit: Number(form.get('daily_limit') ?? 15)
		});

		if (next) {
			applySession(next);
			if (!TERMINAL.includes(next.status)) startPolling(next.session_id);
		}
	}

	async function confirm() {
		if (!session) return;
		const next = await send(`/accounts/login/${session.session_id}/confirm`);
		if (next) applySession(next);
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
			<Button {...props}>Добавить аккаунт</Button>
		{/snippet}
	</Dialog.Trigger>
	<Dialog.Content class="sm:max-w-3xl">
		<Dialog.Header>
			<Dialog.Title>Новый аккаунт Авито</Dialog.Title>
			<Dialog.Description>
				Бот откроет браузер, вы войдёте в аккаунт сами, бот сохранит сессию. Логин и пароль
				панель не спрашивает и нигде не хранит.
			</Dialog.Description>
		</Dialog.Header>

		{#if !session}
			<form class="space-y-4" onsubmit={openBrowser}>
				<div class="space-y-2">
					<Label for="login-field">Название аккаунта</Label>
					<Input id="login-field" name="login" autocomplete="off" required />
					<p class="text-muted-foreground text-xs">
						Только для отображения в панели, например номер телефона или метка «основной».
					</p>
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
						{busy ? 'Открываем браузер...' : 'Открыть браузер'}
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

				{#if session.status === 'waiting_for_operator' && session.remote_view_url}
					<p class="text-sm">
						Войдите в аккаунт Авито в окне ниже: почта или телефон, пароль, код из СМС,
						проверка, если попросит. Когда увидите, что вы вошли, нажмите кнопку под окном.
					</p>
					<div class="border-border overflow-hidden rounded-md border">
						<iframe
							src={session.remote_view_url}
							title="Браузер бота"
							class="h-[34rem] w-full"
						></iframe>
					</div>
					<p class="text-muted-foreground text-xs">
						Окно просит пароль VNC. Не открывайте этот порт наружу: за ним браузер, который
						станет рабочей сессией аккаунта.
					</p>
					<Button disabled={busy} onclick={confirm}>
						{busy ? 'Проверяем...' : 'Я вошёл, сохранить сессию'}
					</Button>
					{#if session.hint}
						<p class="text-muted-foreground text-sm">{session.hint}</p>
					{/if}
				{:else if session.status === 'starting' || session.status === 'saving'}
					<p class="text-muted-foreground text-sm">Секунду, готовим браузер.</p>
				{:else if session.hint}
					<p class="text-sm">{session.hint}</p>
				{/if}

				{#if errorMessage}
					<p class="text-destructive text-sm" role="alert">{errorMessage}</p>
				{/if}

				{#if session.has_screenshot && session.status !== 'waiting_for_operator'}
					<details class="text-sm">
						<summary class="cursor-pointer">Что показывает Авито</summary>
						<img
							src={`/accounts/login/${session.session_id}/screenshot`}
							alt="Экран браузера бота"
							class="border-border mt-2 w-full rounded-md border"
						/>
					</details>
				{/if}

				<Dialog.Footer>
					<Button variant="outline" onclick={cancel}>Закрыть</Button>
				</Dialog.Footer>
			</div>
		{/if}
	</Dialog.Content>
</Dialog.Root>
