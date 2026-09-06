<script lang="ts">
	import { enhance } from '$app/forms';
	import { toast } from 'svelte-sonner';
	import { Badge } from '$lib/ui/badge/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import { StatCard } from '$lib/ui/stat-card/index.js';
	import { Switch } from '$lib/ui/switch/index.js';
	import * as Table from '$lib/ui/table/index.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let pauseForm: HTMLFormElement | null = $state(null);

	const nextWindow = $derived(
		data.stats?.next_window_at
			? new Date(data.stats.next_window_at).toLocaleString('ru-RU', {
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

<svelte:head><title>Дашборд</title></svelte:head>

<div class="space-y-6">
	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	{#if data.stats}
		{@const stats = data.stats}

		<Card.Root>
			<Card.Header>
				<Card.Title>Управление ботом</Card.Title>
				<Card.Description>
					{#if stats.window_open_now}
						Окно открыто, отправка идёт
					{:else}
						Отправка остановлена: {stats.closed_reason}{nextWindow
							? '. Следующее окно: ' + nextWindow
							: ''}
					{/if}
				</Card.Description>
				<Card.Action>
					<div class="flex items-center gap-3">
						<form method="POST" action="?/pause" use:enhance bind:this={pauseForm}>
							<input type="hidden" name="paused" value={String(!stats.paused)} />
							<Switch
								checked={!stats.paused}
								aria-label="Запустить или поставить бота на паузу"
								onCheckedChange={() => pauseForm?.requestSubmit()}
							/>
						</form>
						<Badge variant={stats.paused ? 'secondary' : 'default'}>
							{stats.paused ? 'на паузе' : 'запущен'}
						</Badge>
					</div>
				</Card.Action>
			</Card.Header>
		</Card.Root>

		<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
			<StatCard label="Отправлено всего" value={stats.messages_sent} hint="сообщений" />
			<StatCard
				label="Отправлено сегодня"
				value={stats.messages_today}
				hint={'запас на сегодня: ' + stats.capacity_today}
				trend={stats.capacity_today > 0 ? 'up' : 'down'}
			/>
			<StatCard
				label="Лиды"
				value={stats.leads_delivered}
				hint="доставлено в Telegram"
				trend={stats.leads_delivered > 0 ? 'up' : 'flat'}
			/>
			<StatCard
				label="Ошибки отправки"
				value={stats.messages_failed}
				trend={stats.messages_failed > 0 ? 'down' : 'flat'}
			/>
		</div>

		<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
			<StatCard label="Продавцов найдено" value={stats.sellers_total} />
			<StatCard label="В переписке" value={stats.sellers_contacted} />
			<StatCard label="Заинтересованы" value={stats.sellers_interested} trend="up" />
			<StatCard label="Отказались" value={stats.sellers_rejected} trend="down" />
		</div>

		<div class="grid gap-6 lg:grid-cols-2">
			<Card.Root>
				<Card.Header>
					<Card.Title>Этапы переписки</Card.Title>
					<Card.Description>Сколько сообщений ушло на каждом этапе</Card.Description>
				</Card.Header>
				<Card.Content>
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head>Этап</Table.Head>
								<Table.Head class="text-right">Отправлено</Table.Head>
								<Table.Head class="text-right">Ошибки</Table.Head>
								<Table.Head class="text-right">Пропущено</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each stats.stages as row (row.stage)}
								<Table.Row>
									<Table.Cell class="font-medium">Этап {row.stage}</Table.Cell>
									<Table.Cell class="text-right tabular-nums">{row.sent}</Table.Cell>
									<Table.Cell class="text-right tabular-nums">{row.failed}</Table.Cell>
									<Table.Cell class="text-right tabular-nums">{row.skipped}</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>Состояние сервисов</Card.Title>
					<Card.Description>Бэкенд, планировщик и аккаунты</Card.Description>
				</Card.Header>
				<Card.Content class="space-y-3">
					<div class="flex items-center justify-between">
						<span class="text-sm">API</span>
						<Badge variant={data.health ? 'default' : 'destructive'}>
							{data.health ? data.health.status : 'недоступен'}
						</Badge>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-sm">База данных</span>
						<Badge variant={data.health?.database ? 'default' : 'destructive'}>
							{data.health?.database ? 'подключена' : 'нет связи'}
						</Badge>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-sm">Планировщик</span>
						<Badge variant={data.health?.scheduler ? 'default' : 'secondary'}>
							{data.health?.scheduler ? 'работает' : 'остановлен'}
						</Badge>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-sm">Аккаунты в работе</span>
						<Badge variant={stats.accounts_active > 0 ? 'default' : 'destructive'}>
							{stats.accounts_active}
						</Badge>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-sm">Заблокировано</span>
						<Badge variant={stats.accounts_blocked > 0 ? 'destructive' : 'secondary'}>
							{stats.accounts_blocked}
						</Badge>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-sm">Ответов разобрано</span>
						<Badge variant="outline">
							{stats.replies_analyzed} / {stats.replies_total}
						</Badge>
					</div>
				</Card.Content>
			</Card.Root>
		</div>
	{/if}
</div>
