<script lang="ts">
	import { enhance } from '$app/forms';
	import { toast } from 'svelte-sonner';
	import { Badge } from '$lib/ui/badge/index.js';
	import { Button } from '$lib/ui/button/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import { Input } from '$lib/ui/input/index.js';
	import { Label } from '$lib/ui/label/index.js';
	import { StatCard } from '$lib/ui/stat-card/index.js';
	import { Switch } from '$lib/ui/switch/index.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let pauseForm: HTMLFormElement | null = $state(null);

	const weekdays = [
		{ value: 0, label: 'Пн' },
		{ value: 1, label: 'Вт' },
		{ value: 2, label: 'Ср' },
		{ value: 3, label: 'Чт' },
		{ value: 4, label: 'Пт' },
		{ value: 5, label: 'Сб' },
		{ value: 6, label: 'Вс' }
	];

	const enabled = $derived(new Set(data.settings?.weekdays_enabled ?? []));

	const nextWindow = $derived(
		data.settings?.next_window_at
			? new Date(data.settings.next_window_at).toLocaleString('ru-RU', {
					day: '2-digit',
					month: '2-digit',
					hour: '2-digit',
					minute: '2-digit'
				})
			: null
	);

	$effect(() => {
		if (form && 'message' in form && form.message) {
			toast.success(form.message);
		}
	});
</script>

<svelte:head><title>Расписание</title></svelte:head>

<div class="space-y-6">
	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	{#if data.settings}
		{@const settings = data.settings}
		<div class="grid gap-4 sm:grid-cols-3">
			<StatCard
				label="Окно отправки"
				value={settings.window_start + ':00–' + settings.window_end + ':00'}
				hint={settings.timezone}
			/>
			<StatCard
				label="Задержка"
				value={settings.delay_min_minutes + '–' + settings.delay_max_minutes + ' мин'}
				hint="между сообщениями"
			/>
			<StatCard
				label="Суточный лимит"
				value={settings.daily_limit}
				hint="на один аккаунт"
			/>
		</div>

		<Card.Root>
			<Card.Header>
				<Card.Title>Состояние бота</Card.Title>
				<Card.Description>
					Настройки применяются сразу, перезапуск не нужен
				</Card.Description>
				<Card.Action>
					<div class="flex items-center gap-3">
						<form method="POST" action="?/pause" use:enhance bind:this={pauseForm}>
							<input type="hidden" name="paused" value={String(!settings.paused)} />
							<Switch
								checked={!settings.paused}
								aria-label="Запустить или поставить бота на паузу"
								onCheckedChange={() => pauseForm?.requestSubmit()}
							/>
						</form>
						<Badge variant={settings.paused ? 'secondary' : 'default'}>
							{settings.paused ? 'на паузе' : 'запущен'}
						</Badge>
					</div>
				</Card.Action>
			</Card.Header>
			<Card.Content>
				{#if settings.window_open_now}
					<p class="text-sm">Окно открыто, отправка идёт.</p>
				{:else}
					<p class="text-muted-foreground text-sm">
						Отправка остановлена: {settings.closed_reason}.
						{#if nextWindow}
							Следующее окно: {nextWindow}.
						{/if}
					</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Окно отправки</Card.Title>
				<Card.Description>Часы и дни недели, когда бот пишет продавцам</Card.Description>
			</Card.Header>
			<form method="POST" action="?/schedule" use:enhance>
				<Card.Content class="space-y-4">
					<div class="grid gap-4 sm:grid-cols-2">
						<div class="space-y-2">
							<Label for="window_start">Начало, час</Label>
							<Input
								id="window_start"
								name="window_start"
								type="number"
								min="0"
								max="23"
								value={settings.window_start}
								required
							/>
						</div>
						<div class="space-y-2">
							<Label for="window_end">Конец, час</Label>
							<Input
								id="window_end"
								name="window_end"
								type="number"
								min="1"
								max="24"
								value={settings.window_end}
								required
							/>
						</div>
					</div>
					<fieldset class="space-y-2">
						<legend class="text-sm font-medium">Дни недели</legend>
						<div class="flex flex-wrap gap-3">
							{#each weekdays as day (day.value)}
								<label class="flex items-center gap-2 text-sm">
									<input
										type="checkbox"
										name="weekdays"
										value={day.value}
										checked={enabled.has(day.value)}
										class="accent-primary size-4"
									/>
									{day.label}
								</label>
							{/each}
						</div>
					</fieldset>
					{#if form?.message}
						<p class="text-destructive text-sm" role="alert">{form.message}</p>
					{/if}
				</Card.Content>
				<Card.Footer class="mt-4">
					<Button type="submit">Сохранить окно</Button>
				</Card.Footer>
			</form>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title>Лимиты и ротация</Card.Title>
				<Card.Description>
					Домен зажимает значения по политике: задержка 5–15 мин, ротация 2–3 аккаунта
				</Card.Description>
			</Card.Header>
			<form method="POST" action="?/limits" use:enhance>
				<Card.Content class="grid gap-4 sm:grid-cols-3">
					<div class="space-y-2">
						<Label for="delay_min_minutes">Задержка от, мин</Label>
						<Input
							id="delay_min_minutes"
							name="delay_min_minutes"
							type="number"
							min="5"
							max="15"
							value={settings.delay_min_minutes}
							required
						/>
					</div>
					<div class="space-y-2">
						<Label for="delay_max_minutes">Задержка до, мин</Label>
						<Input
							id="delay_max_minutes"
							name="delay_max_minutes"
							type="number"
							min="5"
							max="15"
							value={settings.delay_max_minutes}
							required
						/>
					</div>
					<div class="space-y-2">
						<Label for="account_rotation_size">Аккаунтов в ротации</Label>
						<Input
							id="account_rotation_size"
							name="account_rotation_size"
							type="number"
							min="2"
							max="3"
							value={settings.account_rotation_size}
							required
						/>
					</div>
				</Card.Content>
				<Card.Footer class="mt-4">
					<Button type="submit">Сохранить лимиты</Button>
				</Card.Footer>
			</form>
		</Card.Root>
	{/if}
</div>
