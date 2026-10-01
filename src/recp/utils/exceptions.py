
class RecpError(Exception):
    pass


class RecipeError(RecpError):
    pass


class RequiredValueNotFoundError(RecpError):
    pass


class MinimumVersionRequirementError(RecpError):
    pass


class FolderNotFoundError(RecpError):
    pass


class FileExtensionError(RecpError):
    pass


class LengthError(RecpError):
    pass
