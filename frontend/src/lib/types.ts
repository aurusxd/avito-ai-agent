export type Stage = 1 | 2 | 3;

export type SellerStatus = 'new' | 'contacted' | 'interested' | 'lead' | 'rejected';

export type MessageStatus = 'sent' | 'failed' | 'skipped';

export type Sentiment = 'interested' | 'neutral' | 'negative';

export type Category = {
	id: number;
	name: string;
	avito_url_or_slug: string;
	region: string;
	min_listings_per_seller: number;
	enabled: boolean;
};

export type CategoryCreate = Omit<Category, 'id'>;

export type CategoryUpdate = Partial<CategoryCreate>;


export type AccountStatus = 'active' | 'paused' | 'banned';

export type Account = {
	id: number;
	login: string;
	session_storage_path: string;
	status: AccountStatus;
	daily_limit: number;
	daily_message_count: number;
	remaining_today: number;
	has_session: boolean;
	last_reset_at: string;
	created_at: string;
};

export type AccountCreate = {
	login: string;
	session_storage_path: string;
	daily_limit: number;
};

export type AccountUpdate = Partial<AccountCreate> & { status?: AccountStatus };

export type RotationMember = {
	account_id: number;
	login: string;
	status: AccountStatus;
	remaining_today: number;
	in_rotation: boolean;
	available: boolean;
};

export type RotationPreview = {
	rotation_size: number;
	delay_min_minutes: number;
	delay_max_minutes: number;
	daily_limit: number;
	next_account_id: number | null;
	capacity_today: number;
	members: RotationMember[];
};


export type ApiErrorBody = {
	error: {
		code: string;
		message: string;
		details?: unknown;
	};
};

export type Seller = {
	id: number;
	avito_seller_id: string;
	name: string;
	profile_url: string;
	listings_count: number;
	region: string;
	status: SellerStatus;
	category_id: number;
	created_at: string;
};

export type ParserRunResult = {
	category_id: number;
	sellers_matched: number;
	sellers_created: number;
	sellers_updated: number;
	listings_created: number;
	listings_updated: number;
};
