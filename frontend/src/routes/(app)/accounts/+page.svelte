<script lang="ts">
	import { enhance } from "$app/forms";
	import { toast } from "svelte-sonner";
	import { Badge } from "$lib/ui/badge/index.js";
	import { Button } from "$lib/ui/button/index.js";
	import * as Card from "$lib/ui/card/index.js";
	import * as Dialog from "$lib/ui/dialog/index.js";
	import { Input } from "$lib/ui/input/index.js";
	import { Label } from "$lib/ui/label/index.js";
	import { StatCard } from "$lib/ui/stat-card/index.js";
	import { Switch } from "$lib/ui/switch/index.js";
	import * as Table from "$lib/ui/table/index.js";
	import type { AccountStatus } from "$lib/types";
	import type { ActionData, PageData } from "./$types";
	import AccountLoginDialog from "./AccountLoginDialog.svelte";

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let createOpen = $state(false);
	let toggleForms: Record<number, HTMLFormElement | null> = $state({});

	const statusLabel: Record<AccountStatus, string> = {
		active: "активен",
		paused: "на паузе",
		banned: "заблокирован",
	};

	const statusVariant: Record<
		AccountStatus,
		"default" | "secondary" | "destructive"
	> = {
		active: "default",
		paused: "secondary",
		banned: "destructive",
	};

	const activeCount = $derived(
		data.accounts.filter((item) => item.status === "active").length,
	);
	const bannedCount = $derived(
		data.accounts.filter((item) => item.status === "banned").length,
	);
	const rotationIds = $derived(
		new Set(
			(data.rotation?.members ?? [])
				.filter((m) => m.in_rotation)
				.map((m) => m.account_id),
		),
	);

	$effect(() => {
		if (form && "message" in form && form.message) {
			toast.success(form.message);
		}
	});
</script>

<svelte:head><title>Аккаунты</title></svelte:head>

<div class="space-y-6">
	<div class="grid gap-4 sm:grid-cols-4">
		<StatCard label="Всего аккаунтов" value={data.accounts.length} />
		<StatCard
			label="Активных"
			value={activeCount}
			trend="up"
			hint="участвуют в отправке"
		/>
		<StatCard
			label="Заблокировано"
			value={bannedCount}
			trend={bannedCount ? "down" : "flat"}
		/>
		<StatCard
			label="Запас на сегодня"
			value={data.rotation?.capacity_today ?? 0}
			hint="сообщений по ротации"
		/>
	</div>

	{#if data.loadError}
		<p class="text-destructive text-sm" role="alert">{data.loadError}</p>
	{/if}

	{#if data.rotation}
		<Card.Root>
			<Card.Header>
				<Card.Title>Ротация и лимиты</Card.Title>
				<Card.Description>
					В ротации до {data.rotation.rotation_size} аккаунтов, задержка
					{data.rotation.delay_min_minutes}–{data.rotation
						.delay_max_minutes} мин, лимит
					{data.rotation.daily_limit} сообщений в сутки на аккаунт
				</Card.Description>
			</Card.Header>
			<Card.Content>
				{#if data.rotation.next_account_id}
					{@const next = data.rotation.members.find(
						(m) => m.account_id === data.rotation?.next_account_id,
					)}
					<p class="text-sm">
						Следующим пишет <span class="font-medium"
							>{next?.login}</span
						>, у него осталось
						{next?.remaining_today} сообщений.
					</p>
				{:else}
					<p class="text-muted-foreground text-sm">
						Свободных аккаунтов нет: лимиты выбраны или все аккаунты
						вне работы.
					</p>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}

	<Card.Root>
		<Card.Header>
			<Card.Title>Аккаунты Авито</Card.Title>
			<Card.Description>
				Авторизация только через файл сессии Playwright, пароли панель
				не хранит
			</Card.Description>
			<Card.Action>
				<div class="flex items-center gap-2">
					<AccountLoginDialog />
				<Dialog.Root bind:open={createOpen}>
					<Dialog.Trigger>
						{#snippet child({ props })}
							<Button {...props} variant="outline">Добавить вручную</Button>
						{/snippet}
					</Dialog.Trigger>
					<Dialog.Content class="sm:max-w-md">
						<Dialog.Header>
							<Dialog.Title>Новый аккаунт</Dialog.Title>
							<Dialog.Description>
								Сначала сохраните сессию скриптом входа, затем
								укажите путь к файлу
							</Dialog.Description>
						</Dialog.Header>
						<form
							method="POST"
							action="?/create"
							class="space-y-4"
							use:enhance={() => {
								return async ({ result, update }) => {
									if (result.type === "success")
										createOpen = false;
									await update();
								};
							}}
						>
							<div class="space-y-2">
								<Label for="login">Логин</Label>
								<Input id="login" name="login" required />
							</div>
							<div class="space-y-2">
								<Label for="session_storage_path"
									>Путь к файлу сессии</Label
								>
								<Input
									id="session_storage_path"
									name="session_storage_path"
									placeholder="data/sessions/operator-1.storage.json"
									required
								/>
							</div>
							<div class="space-y-2">
								<Label for="daily_limit">Суточный лимит</Label>
								<Input
									id="daily_limit"
									name="daily_limit"
									type="number"
									min="1"
									max="15"
									value="15"
									required
								/>
							</div>
							{#if form?.message}
								<p
									class="text-destructive text-sm"
									role="alert"
								>
									{form.message}
								</p>
							{/if}
							<Dialog.Footer>
								<Button type="submit">Сохранить</Button>
							</Dialog.Footer>
						</form>
					</Dialog.Content>
				</Dialog.Root>
							</div>
			</Card.Action>
		</Card.Header>
		<Card.Content>
			<div class="overflow-x-auto">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Логин</Table.Head>
							<Table.Head>Сессия</Table.Head>
							<Table.Head class="text-right">Сегодня</Table.Head>
							<Table.Head class="text-center">Лимит</Table.Head>
							<Table.Head>Ротация</Table.Head>
							<Table.Head>Статус</Table.Head>
							<Table.Head class="text-right">Действия</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each data.accounts as account (account.id)}
							<Table.Row>
								<Table.Cell class="font-medium"
									>{account.login}</Table.Cell
								>
								<Table.Cell>
									<Badge
										variant={account.has_session
											? "default"
											: "destructive"}
									>
										{account.has_session
											? "найдена"
											: "нет файла"}
									</Badge>
								</Table.Cell>
								<Table.Cell class="text-right tabular-nums">
									{account.daily_message_count} / {account.daily_limit}
								</Table.Cell>
								<Table.Cell class="text-center">
									<form
										method="POST"
										action="?/limit"
										use:enhance
										class="flex items-center justify-center gap-2"
									>
										<input
											type="hidden"
											name="id"
											value={account.id}
										/>
										<Input
											name="daily_limit"
											type="number"
											min="1"
											max="15"
											value={account.daily_limit}
											class="h-8 w-16 text-right"
											aria-label={"Суточный лимит для " +
												account.login}
										/>
										<Button
											type="submit"
											variant="ghost"
											size="sm">OK</Button
										>
									</form>
								</Table.Cell>
								<Table.Cell>
									{#if rotationIds.has(account.id)}
										<Badge variant="outline"
											>в ротации</Badge
										>
									{:else}
										<span
											class="text-muted-foreground text-sm"
											>резерв</span
										>
									{/if}
								</Table.Cell>
								<Table.Cell>
									<div class="flex items-center gap-2">
										<form
											method="POST"
											action="?/toggle"
											use:enhance
											bind:this={toggleForms[account.id]}
										>
											<input
												type="hidden"
												name="id"
												value={account.id}
											/>
											<input
												type="hidden"
												name="status"
												value={account.status ===
												"active"
													? "paused"
													: "active"}
											/>
										</form>
										<Badge
											variant={statusVariant[
												account.status
											]}
										>
											{statusLabel[account.status]}
										</Badge>
									</div>
								</Table.Cell>
								<Table.Cell class="text-right">
									<form
										method="POST"
										action="?/remove"
										use:enhance
									>
										<input
											type="hidden"
											name="id"
											value={account.id}
										/>
										<Button
											type="submit"
											variant="ghost"
											size="sm">Удалить</Button
										>
									</form>
								</Table.Cell>
								<Table.Cell>
									<form
										method="POST"
										action="?/toggle"
										use:enhance
										bind:this={toggleForms[account.id]}
									>
										<input
											type="hidden"
											name="id"
											value={account.id}
										/>
										<input
											type="hidden"
											name="status"
											value={account.status === "active"
												? "paused"
												: "active"}
										/>
										<Switch
											checked={account.status ===
												"active"}
											disabled={account.status ===
												"banned"}
											aria-label={"Переключить аккаунт " +
												account.login}
											onCheckedChange={() =>
												toggleForms[
													account.id
												]?.requestSubmit()}
										/>
									</form>
								</Table.Cell>
							</Table.Row>
						{:else}
							<Table.Row>
								<Table.Cell
									colspan={7}
									class="text-muted-foreground py-10 text-center"
								>
									Аккаунтов пока нет
								</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			</div>
		</Card.Content>
	</Card.Root>
</div>
