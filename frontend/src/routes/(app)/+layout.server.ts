import { redirect } from '@sveltejs/kit';
import { PANEL_TOKEN_COOKIE } from '$lib/api';
import { navItems } from '$lib/nav';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = ({ cookies, url }) => {
	if (!cookies.get(PANEL_TOKEN_COOKIE)) {
		redirect(303, '/login?redirectTo=' + encodeURIComponent(url.pathname));
	}

	return {
		nav: navItems,
		currentPath: url.pathname
	};
};
