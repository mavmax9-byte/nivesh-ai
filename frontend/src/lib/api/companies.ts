import { apiClient } from "@/lib/api-client";
import type { Company } from "@/lib/api/types";

export function listCompanies(limit = 200): Promise<Company[]> {
  return apiClient.get<Company[]>("/companies", { params: { limit } });
}

export function getCompany(symbol: string): Promise<Company> {
  return apiClient.get<Company>(`/companies/${encodeURIComponent(symbol)}`);
}
