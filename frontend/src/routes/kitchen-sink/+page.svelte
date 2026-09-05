<script lang="ts">
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
	import * as Table from '$lib/ui/table/index.js';
	import { Textarea } from '$lib/ui/textarea/index.js';

	const buttonVariants = ['default', 'secondary', 'destructive', 'outline', 'ghost', 'link'] as const;
	const badgeVariants = ['default', 'secondary', 'destructive', 'outline'] as const;
	const stages = [
		{ value: '1', label: 'Этап 1' },
		{ value: '2', label: 'Этап 2' },
		{ value: '3', label: 'Этап 3' }
	];

	let stage = $state('1');
	let running = $state(true);
	let dialogOpen = $state(false);

	const stageLabel = $derived(stages.find((item) => item.value === stage)?.label ?? 'Этап');
</script>

<svelte:head><title>Kitchen sink</title></svelte:head>

<main class="mx-auto max-w-4xl space-y-8 p-6">
	<header>
		<h1 class="text-2xl font-semibold">Kitchen sink</h1>
		<p class="text-muted-foreground text-sm">Все UI-примитивы панели в одном месте</p>
	</header>

	<section class="space-y-3">
		<h2 class="text-lg font-medium">Button</h2>
		<div class="flex flex-wrap gap-2">
			{#each buttonVariants as variant (variant)}
				<Button {variant}>{variant}</Button>
			{/each}
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Button size="sm">sm</Button>
			<Button size="default">default</Button>
			<Button size="lg">lg</Button>
			<Button disabled>disabled</Button>
		</div>
	</section>

	<section class="space-y-3">
		<h2 class="text-lg font-medium">Badge</h2>
		<div class="flex flex-wrap gap-2">
			{#each badgeVariants as variant (variant)}
				<Badge {variant}>{variant}</Badge>
			{/each}
		</div>
	</section>

	<section class="space-y-3">
		<h2 class="text-lg font-medium">Input, Textarea, Select, Switch</h2>
		<div class="grid gap-4 sm:grid-cols-2">
			<div class="space-y-2">
				<Label for="ks-input">Название категории</Label>
				<Input id="ks-input" placeholder="Бани" />
			</div>
			<div class="space-y-2">
				<Label for="ks-select">Этап переписки</Label>
				<Select.Root type="single" bind:value={stage}>
					<Select.Trigger id="ks-select" class="w-full">{stageLabel}</Select.Trigger>
					<Select.Content>
						{#each stages as item (item.value)}
							<Select.Item value={item.value} label={item.label}>{item.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
			<div class="space-y-2 sm:col-span-2">
				<Label for="ks-textarea">Шаблон сообщения</Label>
				<Textarea id="ks-textarea" rows={3} value={'Здравствуйте, {name}! Ваш «{product}» актуален?'} />
			</div>
			<div class="flex items-center gap-3">
				<Switch id="ks-switch" bind:checked={running} />
				<Label for="ks-switch">{running ? 'Бот запущен' : 'Бот на паузе'}</Label>
			</div>
		</div>
	</section>

	<section class="space-y-3">
		<h2 class="text-lg font-medium">Card и StatCard</h2>
		<div class="grid gap-4 sm:grid-cols-3">
			<StatCard label="Отправлено" value={128} hint="за сутки" trend="up" />
			<StatCard label="Отказы" value={4} hint="за сутки" trend="down" />
			<StatCard label="Лиды" value={11} hint="без изменений" trend="flat" />
		</div>
		<Card.Root>
			<Card.Header>
				<Card.Title>Карточка</Card.Title>
				<Card.Description>Описание блока</Card.Description>
				<Card.Action><Button variant="outline" size="sm">Действие</Button></Card.Action>
			</Card.Header>
			<Card.Content>
				<p class="text-sm">Контент карточки.</p>
			</Card.Content>
			<Card.Footer>
				<p class="text-muted-foreground text-sm">Подвал карточки</p>
			</Card.Footer>
		</Card.Root>
	</section>

	<section class="space-y-3">
		<h2 class="text-lg font-medium">Table</h2>
		<div class="overflow-x-auto">
			<Table.Root>
				<Table.Caption>Последние отправки</Table.Caption>
				<Table.Header>
					<Table.Row>
						<Table.Head>Продавец</Table.Head>
						<Table.Head>Этап</Table.Head>
						<Table.Head class="text-right">Статус</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					<Table.Row>
						<Table.Cell>Артём</Table.Cell>
						<Table.Cell>1</Table.Cell>
						<Table.Cell class="text-right"><Badge>отправлено</Badge></Table.Cell>
					</Table.Row>
					<Table.Row>
						<Table.Cell>Ольга</Table.Cell>
						<Table.Cell>2</Table.Cell>
						<Table.Cell class="text-right"><Badge variant="secondary">пропущено</Badge></Table.Cell>
					</Table.Row>
				</Table.Body>
			</Table.Root>
		</div>
	</section>

	<section class="space-y-3">
		<h2 class="text-lg font-medium">Modal и Toast</h2>
		<div class="flex flex-wrap gap-2">
			<Dialog.Root bind:open={dialogOpen}>
				<Dialog.Trigger>
					{#snippet child({ props })}
						<Button {...props}>Открыть модалку</Button>
					{/snippet}
				</Dialog.Trigger>
				<Dialog.Content class="sm:max-w-md">
					<Dialog.Header>
						<Dialog.Title>Подтверждение</Dialog.Title>
						<Dialog.Description>Пример модального окна панели</Dialog.Description>
					</Dialog.Header>
					<Dialog.Footer>
						<Button variant="outline" onclick={() => (dialogOpen = false)}>Отмена</Button>
						<Button onclick={() => (dialogOpen = false)}>Подтвердить</Button>
					</Dialog.Footer>
				</Dialog.Content>
			</Dialog.Root>
			<Button variant="outline" onclick={() => toast.success('Настройки сохранены')}>
				Toast: успех
			</Button>
			<Button variant="outline" onclick={() => toast.error('Аккаунт заблокирован')}>
				Toast: ошибка
			</Button>
		</div>
	</section>
</main>
