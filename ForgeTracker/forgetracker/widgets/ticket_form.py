import ew
from allura.lib.widgets import form_fields as ffw

from pylons import c
from forgetracker import model
from formencode import validators as fev

class TicketCustomFields(ew.CompoundField):
    template='jinja:tracker_widgets/ticket_custom_fields.html'

    @property
    def fields(self):
        # milestone is kind of special because of the layout
        # add it to the main form rather than handle with the other customs
        fields = []
        for cf in c.app.globals.custom_fields:
            if cf.name != '_milestone':
                fields.append(TicketCustomField.make(cf))
        return fields

class GenericTicketForm(ew.SimpleForm):
    name="ticket_form"
    submit_text='Save'
    ticket=None
    show_comment = False
    params=['submit_text','ticket', 'show_comment']

    def display_field_by_name(self, idx, ignore_errors=False):
        field = self.fields[idx]
        ctx = c.widget.context_for(field.name)
        display = field.display(**ctx)
        if ctx['errors'] and field.show_errors and not ignore_errors:
            display = "%s<div class='error'>%s</div>" % (display, ctx['errors'])
        return display

    @property
    def fields(self):
        fields = [
            ew.TextField(name='summary', label='Title',
                attrs={'style':'width: 425px'},
                validator=fev.UnicodeString(not_empty=True, messages={'empty':"You must provide a Title"})),
            ffw.MarkdownEdit(label='Description',name='description',
                    attrs={'style':'width: 100%'}),
            ew.SingleSelectField(name='status', label='Status',
                options=lambda: c.app.globals.all_status_names.split()),
            ffw.ProjectUserSelect(name='assigned_to', label='Assigned To'),
            ffw.LabelEdit(label='Labels',name='labels', className='ticket_form_tags'),
            ffw.FileChooser(name='attachment', label='Attachment', field_type='file', validator=fev.FieldStorageUploadConverter(if_missing=None)),
            ew.TextArea(name='comment', label='Comment'),
            ew.SubmitButton(label=self.submit_text,name='submit',
                attrs={'class':"ui-button ui-widget ui-state-default ui-button-text-only"}),
            ew.HiddenField(name='ticket_num', validator=fev.Int(if_missing=None)),
            ew.HiddenField(name='super_id', validator=fev.UnicodeString(if_missing=None)) ]
        # milestone is kind of special because of the layout
        # add it to the main form rather than handle with the other customs
        if c.app.globals.custom_fields:
            for cf in c.app.globals.custom_fields:
                if cf.name == '_milestone':
                    fields.append(TicketCustomField.make(cf))
                    break
        return ew.NameList(fields)

class TicketForm(GenericTicketForm):
    template='jinja:tracker_widgets/ticket_form.html'
    @property
    def fields(self):
        fields = ew.NameList(super(TicketForm, self).fields)
        if c.app.globals.custom_fields:
            fields.append(TicketCustomFields(name="custom_fields"))
        return fields

class TicketCustomField(object):

    def _select(field):
        options = []
        for opt in field.options.split():
            selected = False
            if opt.startswith('*'):
                opt = opt[1:]
                selected = True
            options.append(ew.Option(label=opt,html_value=opt,py_value=opt,selected=selected))
        return ew.SingleSelectField(label=field.label, name=str(field.name), options=options)

    def _milestone(field):
        options = [ ew.Option(label='None',html_value='',py_value='')]
        for m in field.milestones:
            if not m.complete:
                options.append(ew.Option(
                        label=m.name,
                        py_value=m.name))
        ssf = ew.SingleSelectField(
            label=field.label, name=str(field.name),
            options=options)
        return ssf

    def _boolean(field):
        return ew.Checkbox(label=field.label, name=str(field.name), suppress_label=True)

    def _number(field):
        return ew.NumberField(label=field.label, name=str(field.name))

    @staticmethod
    def _default(field):
        return ew.TextField(label=field.label, name=str(field.name))

    SELECTOR = dict(
        select=_select,
        milestone=_milestone,
        boolean=_boolean,
        sum=_number,
        number=_number)

    @classmethod
    def make(cls, field):
        factory = cls.SELECTOR.get(field.get('type'), cls._default)
        return factory(field)
