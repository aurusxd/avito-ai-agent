<script lang="ts">
	import type { Snippet } from 'svelte';
	import * as Card from '$lib/ui/card/index.js';
	import { cn } from '$lib/utils.js';

	type Trend = 'up' | 'down' | 'flat';

	let {
		label,
		value,
		hint,
		trend = 'flat',
		icon,
		class: className
	}: {
		label: string;
		value: string | number;
		hint?: string;
		trend?: Trend;
		icon?: Snippet;
		class?: string;
	} = $props();

	const trendClass: Record<Trend, string> = {
		up: 'text-emerald-600 dark:text-emerald-400',
		down: 'text-destructive',
		flat: 'text-muted-foreground'
	};

	const trendSign: Record<Trend, string> = { up: '↑', down: '↓', flat: '→' };
</script>

<Card.Root class={cn('gap-2', className)}>
	<Card.Header class="pb-0">
		<Card.Description class="flex items-center gap-2">
			{#if icon}{@render icon()}{/if}
			{label}
		</Card.Description>
		<Card.Title class="text-3xl font-semibold tabular-nums">{value}</Card.Title>
	</Card.Header>
	{#if hint}
		<Card.Content class="pt-0">
			<p class={cn('text-sm', trendClass[trend])}>
				<span aria-hidden="true">{trendSign[trend]}</span>
				{hint}
			</p>
		</Card.Content>
	{/if}
</Card.Root>
