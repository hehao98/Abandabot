/**
 * @id find-dep-usage
 * @name Find dependency usage
 * @description This query finds all source code usage of all dependencies declared in package.json.
 *     It only finds places where the directly imported module/variable/function is used. It does not
 *     track usages of submodules, subfunctions, or any objects/classes created from such usage.
 * @kind problem
 * @precision very-high
 * @severity info
 */

import javascript
import DataFlow

from
  NpmPackage pkg, string name, string file, int impLineno, Import imp, Node use, int useLineno,
  AstNode useNode
where
  (
    pkg.getPackageJson().getDependencies().getADependency(name, _) or
    pkg.getPackageJson().getDevDependencies().getADependency(name, _)
  ) and
  (
    imp.getTopLevel() = pkg.getAModule() and
    file = imp.getFile().getRelativePath() and
    name = imp.getImportedPath().getValue() and
    impLineno = imp.getLocation().getStartLine() and
    use = imp.getImportedModuleNode().getALocalSource().getALocalUse() and
    useLineno = use.getStartLine() and
    useNode = use.getAstNode()
  )
select name, file, useNode, impLineno.toString(), useLineno.toString(),
  useNode.getStartLine().getText()
