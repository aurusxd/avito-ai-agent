export type NavItem = {
	href: string;
	label: string;
	description: string;
};

export const navItems: NavItem[] = [
	{ href: '/dashboard', label: 'Дашборд', description: 'Статистика и управление ботом' },
	{ href: '/categories', label: 'Категории', description: 'Категории, регионы и фильтры' },
	{ href: '/parser', label: 'Парсер', description: 'Обход категорий и найденные продавцы' },
	{ href: '/scripts', label: 'Скрипты', description: 'Шаблоны сообщений по этапам' },
	{ href: '/schedule', label: 'Расписание', description: 'Окно отправки, задержки и лимиты' },
	{ href: '/accounts', label: 'Аккаунты', description: 'Ротация, суточные лимиты и сессии' }
];
