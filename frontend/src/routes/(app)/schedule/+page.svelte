<script lang="ts">
	import * as Card from '$lib/ui/card/index.js';
</script>

<svelte:head><title>Расписание</title></svelte:head>

<Card.Root>
	<Card.Header>
		<Card.Title>Расписание и лимиты</Card.Title>
		<Card.Description>Окно 9-21, выходные, задержки и суточный лимит</Card.Description>
	</Card.Header>
	<Card.Content>
		<p class="text-muted-foreground text-sm">
			Настройки появятся отдельным слайсом стадии 2.
		</p>
	</Card.Content>
</Card.Root>
