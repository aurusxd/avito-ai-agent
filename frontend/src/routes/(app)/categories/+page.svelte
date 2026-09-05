<script lang="ts">
	import { enhance } from '$app/forms';
	import { toast } from 'svelte-sonner';
	import { Badge } from '$lib/ui/badge/index.js';
	import { Button } from '$lib/ui/button/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import * as Dialog from '$lib/ui/dialog/index.js';
	import { Input } from '$lib/ui/input/index.js';
	import { Label } from '$lib/ui/label/index.js';
	import { StatCard } from '$lib/ui/stat-card/index.js';
	import { Switch } from '$lib/ui/switch/index.js';
	import * as Table from '$lib/ui/table/index.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let createOpen = $state(false);
	let toggleForms: Record<number, HTMLFormElement | null> = $state({});

	const enabledCount = $derived(data.categories.filter((item) => item.enabled).length);

	$effect(() => {
		if (form && 'message' in form && form.message) {
			toast.success(form.message);
		}
	});
</script>

<svelte:head><title>Категории</title></svelte:head>

<div class="space-y-6">
	<div class="grid gap-4 sm:grid-cols-3">
		<StatCard label="Всего категорий" value={data.categories.length} />
		<StatCard label="Активных" value={enabledCount} trend="up" hint="участвуют в парсинге" />
		<StatCard label="Выключено" value={data.categories.length - enabledCount} />
	</div>

	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>Категории парсинга</Card.Title>
			<Card.Description>Ссылки на разделы Авито, регионы и минимум объявлений</Card.Description>
			<Card.Action>
				<Dialog.Root bind:open={createOpen}>
					<Dialog.Trigger>
						{#snippet child({ props })}
							<Button {...props}>Добавить</Button>
						{/snippet}
					</Dialog.Trigger>
					<Dialog.Content class="sm:max-w-md">
						<Dialog.Header>
							<Dialog.Title>Новая категория</Dialog.Title>
							<Dialog.Description>Категория попадёт в очередь парсинга сразу</Dialog.Description>
						</Dialog.Header>
						<form
							method="POST"
							action="?/create"
							class="space-y-4"
							use:enhance={() => {
								return async ({ result, update }) => {
									if (result.type === 'success') createOpen = false;
									await update();
								};
							}}
						>
							<div class="space-y-2">
								<Label for="name">Название</Label>
								<Input id="name" name="name" required />
							</div>
							<div class="space-y-2">
								<Label for="avito_url_or_slug">Ссылка или слаг</Label>
								<Input id="avito_url_or_slug" name="avito_url_or_slug" required />
							</div>
							<div class="space-y-2">
								<Label for="region">Регион</Label>
								<Input id="region" name="region" value="Россия" required />
							</div>
							<div class="space-y-2">
								<Label for="min_listings_per_seller">Минимум объявлений у продавца</Label>
								<Input
									id="min_listings_per_seller"
									name="min_listings_per_seller"
									type="number"
									min="1"
									value="3"
									required
								/>
							</div>
							<label class="flex items-center gap-2 text-sm">
								<input type="checkbox" name="enabled" checked class="accent-primary size-4" />
								Включить сразу
							</label>
							{#if form?.message}
								<p class="text-destructive text-sm" role="alert">{form.message}</p>
							{/if}
							<Dialog.Footer>
								<Button type="submit">Сохранить</Button>
							</Dialog.Footer>
						</form>
					</Dialog.Content>
				</Dialog.Root>
			</Card.Action>
		</Card.Header>
		<Card.Content>
			<div class="overflow-x-auto">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Название</Table.Head>
							<Table.Head>Регион</Table.Head>
							<Table.Head>Ссылка</Table.Head>
							<Table.Head class="text-right">Минимум</Table.Head>
							<Table.Head>Статус</Table.Head>
							<Table.Head class="text-right">Действия</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each data.categories as category (category.id)}
							<Table.Row>
								<Table.Cell class="font-medium">{category.name}</Table.Cell>
								<Table.Cell>{category.region}</Table.Cell>
								<Table.Cell class="text-muted-foreground max-w-[18rem] truncate">
									{category.avito_url_or_slug}
								</Table.Cell>
								<Table.Cell class="text-right tabular-nums">
									{category.min_listings_per_seller}
								</Table.Cell>
								<Table.Cell>
									<div class="flex items-center gap-2">
										<form
							method="POST"
							action="?/toggle"
							use:enhance
							bind:this={toggleForms[category.id]}
						>
											<input type="hidden" name="id" value={category.id} />
											<input type="hidden" name="enabled" value={String(!category.enabled)} />
											<Switch
												checked={category.enabled}
												aria-label={'Переключить категорию ' + category.name}
												onCheckedChange={() => toggleForms[category.id]?.requestSubmit()}
											/>
										</form>
										<Badge variant={category.enabled ? 'default' : 'secondary'}>
											{category.enabled ? 'включена' : 'выключена'}
										</Badge>
									</div>
								</Table.Cell>
								<Table.Cell class="text-right">
									<form method="POST" action="?/remove" use:enhance>
										<input type="hidden" name="id" value={category.id} />
										<Button type="submit" variant="ghost" size="sm">Удалить</Button>
									</form>
								</Table.Cell>
							</Table.Row>
						{:else}
							<Table.Row>
								<Table.Cell colspan={6} class="text-muted-foreground py-10 text-center">
									Категорий пока нет
								</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			</div>
		</Card.Content>
	</Card.Root>
</div>
