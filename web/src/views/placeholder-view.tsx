// AI contribution: 50% or more AI-generated
/**
 * Stand-in for a sidebar screen whose user story is not built yet (#408).
 * Naming the story tells reviewers and testers where the content will come
 * from, instead of showing an empty page.
 */

interface PlaceholderViewProps {
  /** Screen title, matching its sidebar label. */
  title: string;
  /** User story that fills the screen, for example "US-4.1". */
  story: string;
}

/** Show the screen title and which user story fills it. */
export function PlaceholderView({ title, story }: Readonly<PlaceholderViewProps>) {
  return (
    <>
      <h1 className="view-title">{title}</h1>
      <p className="panel view-message">
        This screen is filled by {story}.
      </p>
    </>
  );
}
