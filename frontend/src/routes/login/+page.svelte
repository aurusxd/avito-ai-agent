<script lang="ts">
	import { enhance } from '$app/forms';
	import { Button } from '$lib/ui/button/index.js';
	import * as Card from '$lib/ui/card/index.js';
	import { Input } from '$lib/ui/input/index.js';
	import { Label } from '$lib/ui/label/index.js';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();
</script>

<svelte:head><title>Вход в панель</title></svelte:head>

<main class="flex min-h-screen items-center justify-center p-6">
	<Card.Root class="w-full max-w-sm">
		<Card.Header>
			<Card.Title>Панель Авито-бота</Card.Title>
			<Card.Description>Введите токен доступа к панели</Card.Description>
		</Card.Header>
		<form method="POST" use:enhance>
			<Card.Content class="space-y-4">
				<input type="hidden" name="redirectTo" value={data.redirectTo} />
				<div class="space-y-2">
					<Label for="token">Токен панели</Label>
					<Input id="token" name="token" type="password" autocomplete="current-password" required />
				</div>
				{#if form?.message}
					<p class="text-destructive text-sm" role="alert">{form.message}</p>
				{/if}
			</Card.Content>
			<Card.Footer class="mt-4">
				<Button type="submit" class="w-full">Войти</Button>
			</Card.Footer>
		</form>
	</Card.Root>
</main>
