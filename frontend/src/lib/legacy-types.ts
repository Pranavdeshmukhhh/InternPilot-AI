/** Compatibility payloads for existing unmodelled API responses. New resources use api-types.ts. */
// Kept isolated while old admin/provider JSON responses gain server response models.
export type LegacyItem = Record<string, any>;
export type Perform = <T>(key: string, action: () => Promise<T>, message: string) => Promise<T | null>;
