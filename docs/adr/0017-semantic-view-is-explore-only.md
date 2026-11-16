# A semantic view is an Explore-only contract

A Semantic View answers questions over one Gold fact grain. It is not a physical denormalized table, not a query against Silver, and not part of the Agent Decision Surface. Certifying it does not make it an input to a Trading Decision.

The view has four objects. Dimensions come from gold-approved MDM masters and RDM code sets, and an RDM Dimension names its approved version. Facts stay on that one Gold table. A Join links the fact grain to a Dimension without multiplying the grain. Two Joins may reach the same Dimension when each names a different role. A Metric aggregates facts at that grain. Descriptions and synonyms are words on those objects.

Rejected alternatives were a platform-wide view, querying Silver, treating certification as agent binding, and calling the view's link an MDM relationship. A later explicit decision may bind one view version into the Agent Decision Surface. This skill does not.
