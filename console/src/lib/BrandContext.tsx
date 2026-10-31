import { createContext, useContext } from "react";
import type { PublicStation } from "../api/types";
import type { Brand } from "./brand";

export const BrandContext = createContext<Brand | null>(null);

export function useBrand(): Brand {
  const brand = useContext(BrandContext);
  if (!brand) throw new Error("brand");
  return brand;
}

/**
 * Pour l'onglet Station : la marque de l'image (brand.json), que garde un champ vide, et
 * de quoi poser sur la console les réglages qu'il vient d'enregistrer, sans recharger.
 */
export type StationBinding = {
  imageBrand: Brand;
  applyStation: (station: PublicStation) => void;
};

export const StationContext = createContext<StationBinding | null>(null);

export function useStationBinding(): StationBinding {
  const binding = useContext(StationContext);
  if (!binding) throw new Error("station");
  return binding;
}
