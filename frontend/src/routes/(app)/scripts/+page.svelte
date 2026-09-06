<script lang="ts">
	import { enhance } from '$app/forms';
	import { toast } from 'svelte-sonner';
	import { Badge } from '$lib/ui/badge/index.js';
	import { Button } from '$lib/ui/button/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import * as Dialog from '$lib/ui/dialog/index.js';
	import { Input } from '$lib/ui/input/index.js';
	import { Label } from '$lib/ui/label/index.js';
	import * as Select from '$lib/ui/select/index.js';
	import { StatCard } from '$lib/ui/stat-card/index.js';
	import { Switch } from '$lib/ui/switch/index.js';
	import { Textarea } from '$lib/ui/textarea/index.js';
	import type { Stage } from '$lib/types';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let createOpen = $state(false);
	let createStage = $state('1');
	let toggleForms: Record<number, HTMLFormElement | null> = $state({});

	const stages: Stage[] = [1, 2, 3];
	const stageTitle: Record<Stage, string> = {
		1: 'Этап 1 — первое касание',
		2: 'Этап 2 — напоминание',
		3: 'Этап 3 — финальное предложение'
	};

	const byStage = $derived(
		Object.fromEntries(
			stages.map((stage) => [stage, data.scripts.filter((item) => item.stage === stage)])
		) as Record<Stage, typeof data.scripts>
	);

	const coverageFor = $derived(
		Object.fromEntries(data.coverage.map((row) => [row.stage, row])) as Record<
			Stage,
			(typeof data.coverage)[number] | undefined
		>
	);

	const freeVariants = $derived(
		(stage: string) => {
			const used = new Set(
				data.scripts.filter((item) => String(item.stage) === stage).map((item) => item.variant_index)
			);
			return [1, 2, 3, 4, 5].filter((index) => !used.has(index));
		}
	);

	$effect(() => {
		if (form && 'message' in form && form.message) {
			toast.success(form.message);
		}
	});
</script>

<svelte:head><title>Скрипты</title></svelte:head>

<div class="space-y-6">
	<div class="grid gap-4 sm:grid-cols-3">
		{#each stages as stage (stage)}
			{@const row = coverageFor[stage]}
			<StatCard
				label={'Этап ' + stage}
				value={(row?.active_variants ?? 0) + ' / ' + (row?.variants ?? 0)}
				trend={row?.ready ? 'up' : 'down'}
				hint={row?.ready ? 'активных вариантов' : 'нет активных вариантов'}
			/>
		{/each}
	</div>

	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>Шаблоны сообщений</Card.Title>
			<Card.Description>
				До 5 вариантов на этап. Доступные плейсхолдеры: {'{name}'}, {'{product}'}, {'{category}'}
			</Card.Description>
			<Card.Action>
				<Dialog.Root bind:open={createOpen}>
					<Dialog.Trigger>
						{#snippet child({ props })}
							<Button {...props}>Добавить вариант</Button>
						{/snippet}
					</Dialog.Trigger>
					<Dialog.Content class="sm:max-w-lg">
						<Dialog.Header>
							<Dialog.Title>Новый вариант</Dialog.Title>
							<Dialog.Description>
								ИИ доработает шаблон под получателя, плейсхолдеры подставятся автоматически
							</Dialog.Description>
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
							<div class="grid gap-4 sm:grid-cols-2">
								<div class="space-y-2">
									<Label for="stage">Этап</Label>
									<Select.Root type="single" bind:value={createStage} name="stage">
										<Select.Trigger id="stage" class="w-full">Этап {createStage}</Select.Trigger>
										<Select.Content>
											{#each stages as stage (stage)}
												<Select.Item value={String(stage)} label={'Этап ' + stage}>
													Этап {stage}
												</Select.Item>
											{/each}
										</Select.Content>
									</Select.Root>
								</div>
								<div class="space-y-2">
									<Label for="variant_index">Номер варианта</Label>
									<Input
										id="variant_index"
										name="variant_index"
										type="number"
										min="1"
										max="5"
										value={freeVariants(createStage)[0] ?? 1}
										required
									/>
								</div>
							</div>
							<div class="space-y-2">
								<Label for="template_text">Текст шаблона</Label>
								<Textarea id="template_text" name="template_text" rows={4} required />
							</div>
							<label class="flex items-center gap-2 text-sm">
								<input type="checkbox" name="active" checked class="accent-primary size-4" />
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
	</Card.Root>

	{#each stages as stage (stage)}
		<Card.Root>
			<Card.Header>
				<Card.Title>{stageTitle[stage]}</Card.Title>
				<Card.Description>
					{byStage[stage].length} из 5 вариантов, свободно слотов: {coverageFor[stage]?.free_slots ??
						0}
				</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-4">
				{#each byStage[stage] as script (script.id)}
					<div class="border-border rounded-md border p-4">
						<div class="mb-3 flex items-center justify-between gap-3">
							<div class="flex items-center gap-2">
								<Badge variant="outline">Вариант {script.variant_index}</Badge>
								<Badge variant={script.active ? 'default' : 'secondary'}>
									{script.active ? 'активен' : 'выключен'}
								</Badge>
							</div>
							<div class="flex items-center gap-2">
								<form
									method="POST"
									action="?/toggle"
									use:enhance
									bind:this={toggleForms[script.id]}
								>
									<input type="hidden" name="id" value={script.id} />
									<input type="hidden" name="active" value={String(!script.active)} />
									<Switch
										checked={script.active}
										aria-label={'Переключить вариант ' + script.variant_index}
										onCheckedChange={() => toggleForms[script.id]?.requestSubmit()}
									/>
								</form>
								<form method="POST" action="?/remove" use:enhance>
									<input type="hidden" name="id" value={script.id} />
									<Button type="submit" variant="ghost" size="sm">Удалить</Button>
								</form>
							</div>
						</div>
						<form method="POST" action="?/save" use:enhance class="space-y-2">
							<input type="hidden" name="id" value={script.id} />
							<Textarea
								name="template_text"
								rows={3}
								value={script.template_text}
								aria-label={'Текст варианта ' + script.variant_index}
							/>
							<div class="flex justify-end">
								<Button type="submit" variant="outline" size="sm">Сохранить</Button>
							</div>
						</form>
					</div>
				{:else}
					<p class="text-muted-foreground text-sm">Вариантов пока нет</p>
				{/each}
			</Card.Content>
		</Card.Root>
	{/each}
</div>
