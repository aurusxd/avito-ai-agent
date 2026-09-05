<script lang="ts">
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';
	import { toast } from 'svelte-sonner';
	import { Badge } from '$lib/ui/badge/index.js';
	import { Button } from '$lib/ui/button/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import { Label } from '$lib/ui/label/index.js';
	import * as Select from '$lib/ui/select/index.js';
	import { StatCard } from '$lib/ui/stat-card/index.js';
	import * as Table from '$lib/ui/table/index.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let selectedId = $state(
		untrack(() => String(data.categoryId ?? data.categories[0]?.id ?? ''))
	);
	let running = $state(false);

	const selectedLabel = $derived(
		data.categories.find((item) => String(item.id) === selectedId)?.name ?? 'Выберите категорию'
	);

	const totalListings = $derived(
		data.sellers.reduce((sum, seller) => sum + seller.listings_count, 0)
	);

	const regions = $derived(new Set(data.sellers.map((seller) => seller.region)).size);

	$effect(() => {
		if (form && 'message' in form && form.message) {
			toast.success(form.message);
		}
	});
</script>

<svelte:head><title>Парсер</title></svelte:head>

<div class="space-y-6">
	<div class="grid gap-4 sm:grid-cols-3">
		<StatCard label="Продавцов найдено" value={data.sellers.length} />
		<StatCard label="Объявлений в профилях" value={totalListings} />
		<StatCard label="Регионов" value={regions} />
	</div>

	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>Запуск обхода</Card.Title>
			<Card.Description>
				Парсер берёт объявления категории и оставляет продавцов, у которых в профиле не меньше
				указанного числа активных объявлений
			</Card.Description>
		</Card.Header>
		<Card.Content>
			<form
				method="POST"
				action="?/run"
				class="flex flex-wrap items-end gap-3"
				use:enhance={() => {
					running = true;
					return async ({ update }) => {
						await update();
						running = false;
					};
				}}
			>
				<input type="hidden" name="category_id" value={selectedId} />
				<div class="min-w-56 space-y-2">
					<Label for="category">Категория</Label>
					<Select.Root type="single" bind:value={selectedId}>
						<Select.Trigger id="category" class="w-full">{selectedLabel}</Select.Trigger>
						<Select.Content>
							{#each data.categories as category (category.id)}
								<Select.Item value={String(category.id)} label={category.name}>
									{category.name} · от {category.min_listings_per_seller} объявлений
								</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
				<Button type="submit" disabled={running || data.categories.length === 0}>
					{running ? 'Идёт обход...' : 'Запустить парсер'}
				</Button>
				<Button variant="outline" href={selectedId ? `/parser?category_id=${selectedId}` : '/parser'}>
					Показать продавцов категории
				</Button>
			</form>
			{#if form?.message}
				<p class="text-muted-foreground mt-3 text-sm">{form.message}</p>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header>
			<Card.Title>Найденные продавцы</Card.Title>
			<Card.Description>
				{data.categoryId === null ? 'Все категории' : 'Фильтр по выбранной категории'}
			</Card.Description>
		</Card.Header>
		<Card.Content>
			<div class="overflow-x-auto">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Продавец</Table.Head>
							<Table.Head>Регион</Table.Head>
							<Table.Head class="text-right">Объявлений</Table.Head>
							<Table.Head>Статус</Table.Head>
							<Table.Head>Профиль</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each data.sellers as seller (seller.id)}
							<Table.Row>
								<Table.Cell class="font-medium">{seller.name}</Table.Cell>
								<Table.Cell>{seller.region}</Table.Cell>
								<Table.Cell class="text-right tabular-nums">{seller.listings_count}</Table.Cell>
								<Table.Cell><Badge variant="secondary">{seller.status}</Badge></Table.Cell>
								<Table.Cell>
									<a
										class="text-primary underline-offset-4 hover:underline"
										href={seller.profile_url}
										target="_blank"
										rel="noreferrer noopener"
									>
										{seller.avito_seller_id}
									</a>
								</Table.Cell>
							</Table.Row>
						{:else}
							<Table.Row>
								<Table.Cell colspan={5} class="text-muted-foreground py-10 text-center">
									Продавцов пока нет — запустите обход
								</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			</div>
		</Card.Content>
	</Card.Root>
</div>
