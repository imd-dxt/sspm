// ============================================================================
// JIRA VISUALIZATION QUERIES FOR NEO4J BROWSER
// Open http://localhost:7474  |  Login: neo4j / sspm_neo4j_pass
//
// HOW TO SET NODE CAPTIONS IN THE BROWSER:
//   1. Run any query that returns nodes
//   2. Click a node type in the legend (top of graph panel)
//   3. Click the label pill → choose "caption" as the display property
//   4. Repeat for each node type (JiraUser, JiraProject, JiraGroup)
// ============================================================================


// ============================================================================
// 1. OVERVIEW — what's in the Jira graph?
// ============================================================================

// Count every entity type
MATCH (n {platform: 'jira'})
RETURN labels(n) AS type, count(n) AS count
ORDER BY count DESC;


// ============================================================================
// 2. USERS
// ============================================================================

// All active Jira users
MATCH (u:JiraUser {is_active: true})
RETURN u.caption AS name, u.email, u.account_type, u.is_external
ORDER BY u.caption;

// Service / bot accounts only
MATCH (u:JiraUser)
WHERE u.account_type IN ['app', 'service']
RETURN u.caption AS name, u.email, u.account_type;

// External users (different email domain)
MATCH (u:JiraUser {is_external: true})
RETURN u.caption AS name, u.email, u.email_domain;


// ============================================================================
// 3. PROJECTS
// ============================================================================

// All projects
MATCH (p:JiraProject)
RETURN p.key, p.name, p.project_type, p.has_security_scheme, p.default_permission_scheme
ORDER BY p.key;

// Projects without issue security schemes
MATCH (p:JiraProject)
WHERE p.has_security_scheme = false OR p.has_security_scheme IS NULL
RETURN p.key, p.name, p.project_type;


// ============================================================================
// 4. WHO HAS ACCESS TO WHAT  (most useful for visualization)
// ============================================================================

// Full user → project graph  [VISUALIZE THIS]
MATCH (u:JiraUser)-[r:HAS_ROLE]->(p:JiraProject)
RETURN u, r, p
LIMIT 100;

// Admin assignments only  [VISUALIZE THIS — smaller, cleaner]
MATCH (u:JiraUser)-[r:HAS_ROLE]->(p:JiraProject)
WHERE r.role IN ['Administrators', 'Project Admin']
RETURN u, r, p;

// Focus on one specific project (replace KEY with your project key)
MATCH (u:JiraUser)-[r:HAS_ROLE]->(p:JiraProject {key: 'KEY'})
RETURN u, r, p;

// Focus on one specific user (replace the email)
MATCH (u:JiraUser {email: 'user@company.com'})-[r:HAS_ROLE]->(p:JiraProject)
RETURN u, r, p;

// Count users per project (table view)
MATCH (u:JiraUser)-[:HAS_ROLE]->(p:JiraProject)
RETURN p.key AS project, p.name AS name, count(u) AS users
ORDER BY users DESC;

// Count projects per user (who has the most access?)
MATCH (u:JiraUser)-[:HAS_ROLE]->(p:JiraProject)
RETURN u.caption AS user, u.email AS email, count(p) AS projects
ORDER BY projects DESC;


// ============================================================================
// 5. GROUPS
// ============================================================================

// All groups and their size
MATCH (g:JiraGroup)
WHERE g.is_organization IS NULL OR g.is_organization = false
RETURN g.name, g.member_count
ORDER BY g.member_count DESC;

// Who is in the admin groups?  [VISUALIZE THIS]
MATCH (u:JiraUser)-[:MEMBER_OF]->(g:JiraGroup)
WHERE g.name IN ['jira-administrators', 'jira-system-administrators', 'site-admins']
RETURN u, g;

// Full group membership graph
MATCH (u:JiraUser)-[r:MEMBER_OF]->(g:JiraGroup)
RETURN u, r, g
LIMIT 50;


// ============================================================================
// 6. APPS
// ============================================================================

// All installed apps
MATCH (a:Application {platform: 'jira'})
RETURN a.name, a.vendor, a.scopes, a.enabled
ORDER BY a.name;

// Apps with admin/write scopes
MATCH (a:Application {platform: 'jira'})
WHERE any(s IN a.scopes WHERE s IN ['ADMIN', 'WRITE', 'ACT_AS_USER'])
RETURN a.name, a.vendor, a.scopes;


// ============================================================================
// 7. SECURITY FINDINGS QUERIES
// ============================================================================

// Users with admin on 2+ projects
MATCH (u:JiraUser)-[r:HAS_ROLE]->(p:JiraProject)
WHERE r.role IN ['Administrators', 'Project Admin']
WITH u, count(p) AS admin_count, collect(p.key) AS projects
WHERE admin_count >= 2
RETURN u.caption AS user, u.email, admin_count, projects
ORDER BY admin_count DESC;

// External users with elevated roles
MATCH (u:JiraUser {is_external: true})-[r:HAS_ROLE]->(p:JiraProject)
WHERE r.role IN ['Administrators', 'Project Admin']
RETURN u.email, u.email_domain, p.key, r.role;

// Projects using default permission scheme
MATCH (p:JiraProject {default_permission_scheme: true})
RETURN p.key, p.name, p.permission_scheme_name;


// ============================================================================
// 8. COMPLETE JIRA GRAPH  (use only for small workspaces)
// ============================================================================

MATCH (n {platform: 'jira'})
OPTIONAL MATCH (n)-[r]->(m {platform: 'jira'})
RETURN n, r, m
LIMIT 150;
