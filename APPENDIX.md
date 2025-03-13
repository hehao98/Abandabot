# Appendix

## The Abandabot Prototype in the Need-Finding Interview

The Abandabot prototype is implemented as a web application (see the following screenshot):

![](demo-tool-landing-page.png)

For a JavaScript project, it provides a list of all the project's dependencies, the date of the last commit, a flag for whether the dependency has been flagged as archived on GitHub, as well as the dependency type (normal, development, or peer). See the following screenshot:

![](demo-project-home-page.png)

We included the type of dependency because we hypothesized based on previous conversations with developers that some developers might care more about runtime dependencies or development dependencies depending on their use case, experience, and philosophical beliefs.

For each detection, we implemented a prototype page showing the abandonment details, as shown in the following screenshot:

![](demo-detection-details.png)