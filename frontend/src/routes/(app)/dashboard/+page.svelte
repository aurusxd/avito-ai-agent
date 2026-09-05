<script lang="ts">
	import { Badge } from '$lib/ui/badge/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import { StatCard } from '$lib/ui/stat-card/index.js';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const enabledCount = $derived(data.categories.filter((item) => item.enabled).length);
</script>

<svelte:head><title>Дашборд</title></svelte:head>

<div class="space-y-6">
	<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
		<StatCard label="Активных категорий" value={enabledCount} />
		<StatCard label="Всего категорий" value={data.categories.length} />
		<StatCard label="Отправлено сообщений" value="—" hint="появится со слайсом отправки" />
		<StatCard label="Лидов" value="—" hint="появится со слайсом лидов" />
	</div>

	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>Состояние сервисов</Card.Title>
			<Card.Description>Проверка бэкенда и планировщика</Card.Description>
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
		</Card.Content>
	</Card.Root>
</div>
