# Coffee Shop Recommendation Preferences

When Franco asks for coffee shop recommendations, use **Google Places API** to find options near his home location.

## Display Format
- Name and rating
- Walking distance from home
- Wifi availability (if data is available)
- Opening hours
- One-line summary from reviews

## Sorting
Sort by a combination of **rating + distance** (closer + higher rated = higher up the list).

## Preferences
- **Prefer independent coffee shops over chains**
- **"Within walking distance"** = under 20 minutes on foot (~1 mile radius)

## Home Location
Round Rock, Texas (city-level anchor — use as center point for nearby searches)
