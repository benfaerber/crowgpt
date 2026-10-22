/**
 * The regions a recordist can say they are in.
 *
 * A list rather than a text field, because this string is a grouping key: it
 * decides which captures count as the same population, and free text produces
 * "Utah", "utah", "UT" and "Utah, USA" as four different places within a month.
 * The corpus cannot tell those apart afterwards.
 *
 * Not a complete gazetteer. It covers the countries this project actually has
 * recordists in or is recruiting in — American Crow across the US and Canada,
 * Carrion and Hooded Crow across Germany and the UK — and anything else arrives
 * from a GPS fix, which is accepted verbatim. The list is for choosing, not for
 * validating: a fix that resolves to a region nobody listed is still the truth.
 */

export interface RegionGroup {
  /** ISO country code, which is what the stored value ends with. */
  country: string;
  countryName: string;
  regions: string[];
}

export const REGION_GROUPS: readonly RegionGroup[] = [
  {
    country: "US",
    countryName: "United States",
    regions: [
      "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
      "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
      "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
      "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
      "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
      "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
      "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
      "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
      "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
    ],
  },
  {
    country: "CA",
    countryName: "Canada",
    regions: [
      "Alberta", "British Columbia", "Manitoba", "New Brunswick",
      "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia",
      "Nunavut", "Ontario", "Prince Edward Island", "Quebec", "Saskatchewan",
      "Yukon",
    ],
  },
  {
    // The hooded crows. Tamer around people than American Crows are, which is
    // the reason to recruit here at all.
    country: "DE",
    countryName: "Germany",
    regions: [
      "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
      "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
      "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen",
      "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
    ],
  },
  {
    country: "GB",
    countryName: "United Kingdom",
    regions: ["England", "Northern Ireland", "Scotland", "Wales"],
  },
];

/** The stored form: "Utah, US". */
export function regionKey(region: string, country: string): string {
  return `${region}, ${country}`;
}

/** Every region as it would be stored, for searching. */
export function allRegionKeys(): string[] {
  return REGION_GROUPS.flatMap((group) =>
    group.regions.map((region) => regionKey(region, group.country)),
  );
}

/**
 * Regions matching what has been typed, across every country.
 *
 * Matches the country name too, so typing "germany" finds the Bundesländer —
 * somebody who knows which country they are in does not necessarily know how
 * this list spells their state.
 */
export function searchRegions(query: string): { key: string; group: RegionGroup }[] {
  const needle = query.trim().toLowerCase();
  const out: { key: string; group: RegionGroup }[] = [];
  for (const group of REGION_GROUPS) {
    const countryMatches =
      group.countryName.toLowerCase().includes(needle)
      || group.country.toLowerCase() === needle;
    for (const region of group.regions) {
      if (!needle || countryMatches || region.toLowerCase().includes(needle)) {
        out.push({ key: regionKey(region, group.country), group });
      }
    }
  }
  return out;
}
