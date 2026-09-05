<script lang="ts">
	import { page } from '$app/state';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	const activeItem = $derived(
		data.nav.find((item) => page.url.pathname.startsWith(item.href)) ?? data.nav[0]
	);
</script>

<div class="min-h-screen md:grid md:grid-cols-[16rem_1fr]">
	<aside class="bg-card border-border border-b md:border-r md:border-b-0">
		<div class="px-6 py-5">
			<p class="text-lg font-semibold">Авито-бот</p>
			<p class="text-muted-foreground text-sm">Панель оператора</p>
		</div>
		<nav class="px-3 pb-5" aria-label="Основная навигация">
			<ul class="space-y-1">
				{#each data.nav as item (item.href)}
					{@const active = page.url.pathname.startsWith(item.href)}
					<li>
						<a
							href={item.href}
							aria-current={active ? 'page' : undefined}
							class="hover:bg-accent hover:text-accent-foreground block rounded-md px-3 py-2 text-sm transition-colors aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground aria-[current=page]:font-medium"
						>
							{item.label}
						</a>
					</li>
				{/each}
			</ul>
		</nav>
	</aside>

	<div class="flex min-w-0 flex-col">
		<header class="border-border bg-card border-b px-6 py-4">
			<h1 class="text-xl font-semibold">{activeItem.label}</h1>
			<p class="text-muted-foreground text-sm">{activeItem.description}</p>
		</header>
		<main class="min-w-0 flex-1 p-6">
			{@render children()}
		</main>
	</div>
</div>
