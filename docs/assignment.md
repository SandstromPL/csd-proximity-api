# Objective
Build an API that recommends the 10 closest locations from a given dataset containing 10000 locations.
You will be provided with a CSV file containing: ID, Latitude, Longitude, Category
The locations lie on a 1 × 1 grid. However, some direct links/roads between locations may be missing, similar to a real-world road network. Therefore, straight-line/Euclidean distance may not always represent the appropriate proximity measure

# API Requirements

Your API must accept the following inputs:
- Current Latitude, Current Longitude, Category
  Search, Radius,linkage info
- the route must be "IP/search/" and fields must be (lat,long,cat,rad,link)
The API must return:
- 10 recommended location IDs
- The returned locations should be the closest valid locations matching the requested category and search radius.
- Radius is the circular distance from the current latitude and longitude while distance is the actual traversal distance on grid. So by closest we mean grid distance and being in radius is the circular distance
- link is a txt file containing road linkage information. Each line in the txt file contain space separated a and b indicating linkage between point a and b. a and b are all of the grid.

# Dataset

Attachment Contains:
locations.csv containing approximately 1,000,000 locations with the following columns: [ID, Latitude, Longitude, Category]
No road/link/network information will be provided.
You are free to use any suitable: Algorithm, Data structure, Spatial indexing technique, Database/indexing system, Programming language, Optimization technique

# Evaluation

The API will be tested using 10 hidden queries.
- For each query, we have a precomputed set of 10 true nearest locations.
- The 10 test queries will remain hidden.
- All students will be evaluated using the same set of hidden queries to ensure a fair comparison.
- Every test query will have at least 10 valid locations satisfying the required conditions.
- Your implementation should also be efficient enough to handle a dataset of 10000 locations.

# Submission:
- API Link
- Report

# Marks:
1 correct match with our precomputed result = 1 point
For 10 queries and 10 matches, total = 100 points
API Result Marks = Above Points/10 (Max = 10 )
Report Marks = 10 
