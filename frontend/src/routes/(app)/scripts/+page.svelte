<script lang="ts">
	import * as Card from '$lib/ui/card/index.js';
</script>

<svelte:head><title>Скрипты</title></svelte:head>

<Card.Root>
	<Card.Header>
		<Card.Title>Шаблоны сообщений</Card.Title>
		<Card.Description>3 этапа по 5 вариантов, плейсхолдеры {'{name}'} / {'{product}'} / {'{category}'}</Card.Description>
	</Card.Header>
	<Card.Content>
		<p class="text-muted-foreground text-sm">
			CRUD шаблонов появится отдельным слайсом стадии 2.
		</p>
	</Card.Content>
</Card.Root>
