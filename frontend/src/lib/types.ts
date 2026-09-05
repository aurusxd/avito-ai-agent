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

export type ApiErrorBody = {
	error: {
		code: string;
		message: string;
		details?: unknown;
	};
};
